import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime

# ==========================================
# AUTHENTICATION & SECURITY LAYER
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    if st.session_state.authenticated:
        return True
        
    st.markdown("<h2 style='text-align: center;'>🥏 BAU League Login</h2>", unsafe_allow_html=True)
    with st.form("Login Form"):
        password_input = st.text_input("Enter League Password", type="password")
        submit_login = st.form_submit_button("Access Draft Board")
        
        if submit_login:
            if password_input == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect Password. Please try again.")
    return False

if not check_password():
    st.stop()

# ==========================================
# DATABASE CONNECTIONS & DATA LOADING
# ==========================================
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

@st.cache_data
def load_data():
    response = supabase.table("players").select("*").execute()
    return pd.DataFrame(response.data)

df = load_data()

# Build ID-to-Display-Name mapping dictionary (Prefers First + Last Name)
player_map = {}
if not df.empty:
    for _, row in df.iterrows():
        p_id = row.get('id')
        if pd.isna(p_id):
            continue
            
        fname = str(row.get('First Name', '')).strip() if pd.notna(row.get('First Name')) else ""
        lname = str(row.get('Last Name', '')).strip() if pd.notna(row.get('Last Name')) else ""
        nick = str(row.get('Nickname', '')).strip() if pd.notna(row.get('Nickname')) else ""
        
        full_name = f"{fname} {lname}".strip()
        
        # Use Full Name if available, otherwise fallback to Nickname
        player_map[p_id] = full_name if full_name else nick

st.title("🥏 BAU Management Hub")

tab_lineup, tab_draft, tab_history, tab_roster, tab_add = st.tabs([
    "📋 Lineup", 
    "🤝 Draft Board", 
    "📜 Game History",
    "📊 Roster Overview",
    "➕ Add Player"
])

if "assignments" not in st.session_state:
    st.session_state.assignments = {}
if "team_orders" not in st.session_state:
    st.session_state.team_orders = {}

# Helper function to grab a player's pairing value safely
def get_pairing(pid):
    if df.empty: return 99
    match = df[df['id'] == pid]['Pairing'].values
    return int(match[0]) if len(match) > 0 and pd.notna(match[0]) else 99

# ==========================================
# TAB 1: LINEUP / ATTENDANCE
# ==========================================
with tab_lineup:
    st.header("Today's Attendance")
    st.write("Select everyone who showed up to play today:")
    
    sorted_ids = sorted(list(player_map.keys()), key=lambda x: player_map[x]) if player_map else []
    attendees_ids = st.multiselect(
        "Check-in Players", 
        options=sorted_ids, 
        format_func=lambda x: player_map.get(x, "Unknown Player"),
        key="attendance_list_ids"
    )
    
    if attendees_ids:
        st.success(f"📋 {len(attendees_ids)} players checked in. Go to 'Draft Board' to arrange squads!")
    else:
        st.info("Check boxes next to names above to build your active game-day group.")

# ==========================================
# TAB 2: DRAFT BOARD (MANUAL, AUTO & SCORING)
# ==========================================
with tab_draft:
    st.header("Team Assignments")
    
    if not attendees_ids:
        st.warning("Please check in players on the '📋 Lineup' tab first!")
    else:
        num_teams = st.slider("Number of Teams", 2, 4, 2)
        team_options = ["Unassigned"] + [f"Team {i+1}" for i in range(num_teams)]
        
        with st.expander(f"🔍 View Playmaking Stats ({len(attendees_ids)} Selected)"):
            present_df = df[df['id'].isin(attendees_ids)].copy()
            
            # Override 'Nickname' column display visually with the new Full Names
            present_df['Display Name'] = present_df['id'].map(player_map)
            
            playmaking_cols = [
                'Display Name', 'Pairing', 'Type', 'Throw', 'Both Throws', 
                'Consistent Catch', 'Endurance', 'Fast', 'College', 'Club', 'Developing', 'Notes'
            ]
            actual_playmaking = [c for c in playmaking_cols if c in present_df.columns]
            
            st.dataframe(
                present_df[actual_playmaking].sort_values(by="Display Name"), 
                hide_index=True, use_container_width=True
            )
            
        st.divider()

        # AUTOMATED SNAKE DRAFT
        st.subheader("🎲 Balanced Auto-Draft")
        if st.button("Run Balanced Auto-Draft"):
            present_players = df[df['id'].isin(attendees_ids)].copy()
            sorted_players = present_players.sort_values(by="Pairing", ascending=True, na_position='last')
            
            direction = 1
            current_team_idx = 0
            
            for index, row in sorted_players.iterrows():
                p_id = row['id']
                team_assigned = f"Team {current_team_idx + 1}"
                
                # Update both the internal assignment dictionary AND the UI selectbox widget state
                st.session_state.assignments[p_id] = team_assigned
                st.session_state[f"sel_{p_id}"] = team_assigned
                
                current_team_idx += direction
                if current_team_idx == num_teams:
                    direction = -1
                    current_team_idx = num_teams - 1
                elif current_team_idx == -1:
                    direction = 1
                    current_team_idx = 0
            st.success("Auto-Draft complete!")
            st.rerun()

        st.divider()
        
        # Clean up stale assignments
        for p_id in list(st.session_state.assignments.keys()):
            if p_id not in attendees_ids:
                del st.session_state.assignments[p_id]
                
        # SORTING SELECTION INTERFACE
        st.subheader("Assign & Adjust Players")
        sort_option = st.selectbox(
            "Sort list by:", 
            options=["Name", "Pairing (Best to Worst)", "Position Type"]
        )
        
        active_players_df = df[df['id'].isin(attendees_ids)].copy()
        
        # Add the mapped display name for sorting purposes
        active_players_df['Display Name'] = active_players_df['id'].map(player_map)
        
        if sort_option == "Name":
            active_players_df = active_players_df.sort_values(by="Display Name")
        elif sort_option == "Pairing (Best to Worst)":
            active_players_df = active_players_df.sort_values(by="Pairing", ascending=True, na_position='last')
        elif sort_option == "Position Type":
            active_players_df = active_players_df.sort_values(by=["Type", "Display Name"])
        
        for _, row in active_players_df.iterrows():
            p_id = row['id']
            name_label = player_map.get(p_id, "Unknown")
            p_num = int(row['Pairing']) if pd.notna(row['Pairing']) else "N/A"
            p_type = row['Type'] if pd.notna(row['Type']) else "Cutter"
            
            # Fetch the state directly
            current_assignment = st.session_state.assignments.get(p_id, "Unassigned")
            idx = team_options.index(current_assignment) if current_assignment in team_options else 0
            
            col_lbl, col_sel = st.columns([3, 2])
            with col_lbl:
                st.markdown(f"**{name_label}** *(P{p_num} — {p_type})*")
            with col_sel:
                choice = st.selectbox(
                    "Assign", options=team_options, index=idx, key=f"sel_{p_id}", label_visibility="collapsed"
                )
                st.session_state.assignments[p_id] = choice
                
        st.divider()
        
        # ==========================================
        # LIVE STANDINGS MODULE (With Manual Visual Sorting)
        # ==========================================
        st.subheader("Live Standings & Team Balances")
        team_cols = st.columns(num_teams)
        
        for i in range(num_teams):
            t_name = f"Team {i+1}"
            
            # Get everyone currently assigned to this team
            current_assigned_ids = [p_id for p_id, t in st.session_state.assignments.items() if t == t_name]
            
            # Retrieve the last known display order for this team
            saved_order = st.session_state.team_orders.get(t_name, [])
            
            # Filter out players who were removed from this team
            final_order = [pid for pid in saved_order if pid in current_assigned_ids]
            
            # Identify newly assigned players and add them to the list (sorted by pairing)
            missing_ids = [pid for pid in current_assigned_ids if pid not in final_order]
            missing_ids_sorted = sorted(missing_ids, key=get_pairing)
            final_order.extend(missing_ids_sorted)
            
            # Save the reconciled order back to session state
            st.session_state.team_orders[t_name] = final_order
            
            with team_cols[i]:
                # Calculate team score (Defaulting missing pairings to 15)
                t_score = sum([get_pairing(pid) if get_pairing(pid) != 99 else 15 for pid in final_order])
                st.markdown(f"### {t_name}")
                st.metric(label="Pairing Score", value=t_score)
                
                # Render the players with nudging arrows
                for idx, p_id in enumerate(final_order):
                    p_disp = player_map.get(p_id, "Unknown")
                    p_val = get_pairing(p_id)
                    p_str = f"P{p_val}" if p_val != 99 else "N/A"
                    
                    c1, c2, c3 = st.columns([6, 2, 2])
                    c1.write(f"**{p_disp}** *({p_str})*")
                    
                    if c2.button("🔼", key=f"up_{t_name}_{p_id}"):
                        if idx > 0:
                            # Swap with the player above
                            final_order[idx], final_order[idx-1] = final_order[idx-1], final_order[idx]
                            st.session_state.team_orders[t_name] = final_order
                            st.rerun()
                            
                    if c3.button("🔽", key=f"dn_{t_name}_{p_id}"):
                        if idx < len(final_order) - 1:
                            # Swap with the player below
                            final_order[idx], final_order[idx+1] = final_order[idx+1], final_order[idx]
                            st.session_state.team_orders[t_name] = final_order
                            st.rerun()

        st.divider()

        # FINAL SCORE & HISTORY SAVING
        st.subheader("🏁 Log Match Results")
        with st.form("save_game_form"):
            custom_game_date = st.date_input("Match Date", datetime.date.today())
            
            score_inputs = {}
            score_cols = st.columns(num_teams)
            for i in range(num_teams):
                with score_cols[i]:
                    score_inputs[f"team_{i+1}_score"] = st.number_input(f"Team {i+1} Score", min_value=0, value=0, step=1)
            
            submit_game = st.form_submit_button("Submit Match Results to Cloud Ledger")
            
            if submit_game:
                game_payload = {
                    "game_date": custom_game_date.strftime('%Y-%m-%d'),
                    "num_teams": num_teams,
                    "team_1_score": score_inputs.get("team_1_score"),
                    "team_2_score": score_inputs.get("team_2_score"),
                    "team_3_score": score_inputs.get("team_3_score") if num_teams >= 3 else None,
                    "team_4_score": score_inputs.get("team_4_score") if num_teams == 4 else None
                }
                
                try:
                    game_response = supabase.table("games").insert(game_payload).execute()
                    inserted_game_id = game_response.data[0]['id']
                    
                    roster_batch = []
                    for p_id, assigned_team in st.session_state.assignments.items():
                        if assigned_team != "Unassigned":
                            roster_batch.append({
                                "game_id": inserted_game_id,
                                "player_id": p_id,
                                "team_assigned": assigned_team
                            })
                    
                    if roster_batch:
                        supabase.table("game_rosters").insert(roster_batch).execute()
                        
                    st.success("🎉 Match logged and historic roster archived successfully!")
                    st.balloons()
                except Exception as e:
                    st.error(f"Database error writing records: {e}")

# ==========================================
# GAME HISTORY TAB
# ==========================================
with tab_history:
    st.header("Historic Game Logs")
    
    try:
        games_fetch = supabase.table("games").select("*").order("game_date", desc=True).execute()
        historical_games = games_fetch.data
        
        if not historical_games:
            st.info("No saved matches found in database history.")
        else:
            for gm in historical_games:
                g_id = gm['id']
                g_date = gm['game_date']
                
                score_summary = f"Team 1: {gm['team_1_score']}  |  Team 2: {gm['team_2_score']}"
                if gm['team_3_score'] is not None: score_summary += f"  |  Team 3: {gm['team_3_score']}"
                if gm['team_4_score'] is not None: score_summary += f"  |  Team 4: {gm['team_4_score']}"
                
                with st.expander(f"📅 Match on {g_date} ({gm['num_teams']} Teams)"):
                    st.markdown(f"**Final Scores:** `{score_summary}`")
                    
                    roster_fetch = supabase.table("game_rosters").select("*").eq("game_id", g_id).execute()
                    rost_df = pd.DataFrame(roster_fetch.data)
                    
                    if not rost_df.empty:
                        for team_lbl in sorted(rost_df['team_assigned'].unique()):
                            st.markdown(f"**{team_lbl}**")
                            p_ids = rost_df[rost_df['team_assigned'] == team_lbl]['player_id'].tolist()
                            p_list = [player_map.get(pid, "Unknown Player") for pid in p_ids]
                            st.write(", ".join(sorted(p_list)))
                    else:
                        st.caption("No roster mapping records found for this match.")
    except Exception as e:
        st.error(f"Failed to load match ledger: {e}")

# ==========================================
# TAB 4: ROSTER OVERVIEW & CALCULATED YEARS
# ==========================================
with tab_roster:
    st.header("Complete BAU League Roster")
    
    if df.empty:
        st.info("No records found.")
    else:
        df_display = df.copy()
        if 'id' in df_display.columns:
            df_display = df_display.drop(columns=['id'])
            
        # Swap Nickname column for the Full Display Name mapping 
        df_display['Display Name'] = df['id'].map(player_map)
            
        if 'Date Joined' in df_display.columns:
            converted_dates = pd.to_datetime(df_display['Date Joined'], errors='coerce')
            today_date = datetime.date.today()
            
            df_display['Years in BAU'] = converted_dates.apply(
                lambda x: round((today_date - x.date()).days / 365.25, 1) if pd.notna(x) else 0.0
            )
            
            # Shuffle columns for clean presentation
            cols = list(df_display.columns)
            cols.insert(0, cols.pop(cols.index('Display Name')))
            cols.insert(1, cols.pop(cols.index('Years in BAU')))
            # Remove isolated first/last/nickname fields for an uncluttered read
            if 'First Name' in cols: cols.remove('First Name')
            if 'Last Name' in cols: cols.remove('Last Name')
            if 'Nickname' in cols: cols.remove('Nickname')
            
            df_display = df_display[cols]
            
        st.dataframe(df_display.sort_values(by="Display Name"), hide_index=True, use_container_width=True)

# ==========================================
# TAB 5: ADD A NEW PLAYER
# ==========================================
with tab_add:
    st.header("Add Player to Database")
    with st.form("add_player_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: new_first = st.text_input("First Name").strip()
        with col2: new_last = st.text_input("Last Name").strip()
        new_nick = st.text_input("Nickname (Optional)").strip()
        
        col3, col4 = st.columns(2)
        with col3: new_pairing = st.number_input("Pairing (1-30)", min_value=1, max_value=30, value=15)
        with col4: new_type = st.selectbox("Position", ["Cutter", "Handler", "Hybrid"])
        
        new_throw_range = st.selectbox("Throw Range", ["Short", "Medium", "Long"])
        
        st.write("**Player Traits:**")
        c1, c2 = st.columns(2)
        with c1:
            feat_both = st.checkbox("Both Throws")
            feat_coll = st.checkbox("Played College")
            feat_club = st.checkbox("Played Club")
        with c2:
            feat_catch = st.checkbox("Consistent Catch")
            feat_dev = st.checkbox("Developing Player")
            feat_fast = st.checkbox("Fast / Speed")
            
        new_notes = st.text_area("Notes")
        submitted = st.form_submit_button("Save Player")
        
        if submitted:
            payload = {
                "Nickname": new_nick if new_nick else None, 
                "First Name": new_first, 
                "Last Name": new_last,
                "Pairing": new_pairing, "Type": new_type, "Both Throws": feat_both,
                "College": feat_coll, "Club": feat_club, "Consistent Catch": feat_catch,
                "Developing": feat_dev, "Fast": feat_fast, "Throw": new_throw_range,
                "Notes": new_notes, "Date Joined": datetime.date.today().strftime('%m/%d/%Y'),
                "Status": "Regular"
            }
            
            try:
                supabase.table("players").insert(payload).execute()
                # Friendly display for success message
                saved_name = f"{new_first} {new_last}".strip() if new_first else new_nick
                st.success(f"Added {saved_name}!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")