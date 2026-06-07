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
# DATABASE CONNECTIONS & REAL-TIME FETCHES
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

@st.cache_data(ttl=86400)
def get_roster_stats():
    """Fetches and calculates lifetime stats with a 24-hour cache and pagination."""
    all_rosters = []
    start_idx = 0
    while True:
        r_batch = supabase.table("game_rosters").select("game_id", "player_id").range(start_idx, start_idx + 999).execute()
        all_rosters.extend(r_batch.data)
        if len(r_batch.data) < 1000: 
            break
        start_idx += 1000
    
    g_resp = supabase.table("games").select("id", "game_date").execute()
    
    games_df = pd.DataFrame(g_resp.data)
    rosters_df = pd.DataFrame(all_rosters)
    
    if games_df.empty or rosters_df.empty:
        return {}, {}, {}
        
    history_merged = rosters_df.merge(games_df, left_on="game_id", right_on="id")
    history_merged['game_date'] = pd.to_datetime(history_merged['game_date'], errors='coerce')
    
    current_year = datetime.date.today().year
    
    lifetime_games = history_merged.groupby('player_id')['game_id'].nunique().to_dict()
    lifetime_days = history_merged.groupby('player_id')['game_date'].nunique().to_dict()
    
    current_year_df = history_merged[history_merged['game_date'].dt.year == current_year]
    current_year_days = current_year_df.groupby('player_id')['game_date'].nunique().to_dict()
    
    return lifetime_games, lifetime_days, current_year_days

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
        player_map[p_id] = full_name if full_name else nick

# Helper function to grab a player's pairing value safely
def get_pairing(pid):
    if df.empty: return 99
    match = df[df['id'] == pid]['Pairing'].values
    return int(match[0]) if len(match) > 0 and pd.notna(match[0]) else 99

# Pull active cloud-drafting state from Supabase
def get_cloud_draft():
    res = supabase.table("active_draft").select("*").execute()
    return pd.DataFrame(res.data)

active_draft_df = get_cloud_draft()
attendees_ids = active_draft_df['player_id'].tolist() if not active_draft_df.empty else []


st.title("🥏 BAU Management Hub")

tab_lineup, tab_draft, tab_history, tab_roster, tab_add, tab_edit = st.tabs([
    "📋 Lineup", 
    "🤝 Draft Board", 
    "📜 Game History",
    "📊 Roster Overview",
    "➕ Add Player",
    "✏️ Edit Player"
])

# ==========================================
# TAB 1: SHARED ATTENDANCE / CHECK-IN
# ==========================================
with tab_lineup:
    st.header("Today's Attendance")
    st.write("Checking a player in adds them to the shared cloud draft room instantly.")
    
    sorted_ids = sorted(list(player_map.keys()), key=lambda x: player_map[x]) if player_map else []
    
    selected_attendees = st.multiselect(
        "Check-in Players", 
        options=sorted_ids, 
        default=attendees_ids,
        format_func=lambda x: player_map.get(x, "Unknown Player"),
        key="attendance_list_ids"
    )
    
    if st.button("Save & Sync Checked-In Lineup"):
        for p_id in selected_attendees:
            if p_id not in attendees_ids:
                supabase.table("active_draft").insert({"player_id": p_id, "team_assigned": "Unassigned"}).execute()
        for p_id in attendees_ids:
            if p_id not in selected_attendees:
                supabase.table("active_draft").delete().eq("player_id", p_id).execute()
        st.success("Attendance ledger updated in cloud!")
        st.rerun()

# ==========================================
# TAB 2: LIVE CO-EDIT DRAFT BOARD
# ==========================================
with tab_draft:
    st.header("Team Assignments")
    
    if not attendees_ids:
        st.warning("Please check in players on the '📋 Lineup' tab first!")
    else:
        if st.button("🔄 Sync Board (Pull Partner's Live Edits)"):
            st.rerun()
            
        num_teams = st.slider("Number of Teams", 2, 4, 2)
        team_options = ["Unassigned"] + [f"Team {i+1}" for i in range(num_teams)]
        
        st.subheader("🎲 Balanced Auto-Draft")
        if st.button("Run Balanced Auto-Draft"):
            present_players = df[df['id'].isin(attendees_ids)].copy()
            sorted_players = present_players.sort_values(by="Pairing", ascending=True, na_position='last')
            
            direction = 1
            current_team_idx = 0
            
            for index, row in sorted_players.iterrows():
                p_id = row['id']
                team_assigned = f"Team {current_team_idx + 1}"
                
                supabase.table("active_draft").update({"team_assigned": team_assigned}).eq("player_id", p_id).execute()
                
                current_team_idx += direction
                if current_team_idx == num_teams:
                    direction = -1
                    current_team_idx = num_teams - 1
                elif current_team_idx == -1:
                    direction = 1
                    current_team_idx = 0
            st.success("Auto-Draft committed to Cloud! Refreshing screens...")
            st.rerun()

        st.divider()
        
        st.subheader("Assign & Adjust Players")
        
        # Restored Sorting Capability
        sort_option = st.selectbox(
            "Sort list by:", 
            options=["Name", "Pairing (Best to Worst)", "Position Type"]
        )
        
        active_players_df = df[df['id'].isin(attendees_ids)].copy()
        active_players_df['Display Name'] = active_players_df['id'].map(player_map)
        
        if sort_option == "Name":
            active_players_df = active_players_df.sort_values(by="Display Name")
        elif sort_option == "Pairing":
            active_players_df = active_players_df.sort_values(by="Pairing", ascending=True, na_position='last')
        elif sort_option == "Position Type":
            active_players_df = active_players_df.sort_values(by=["Type", "Display Name"])
        
        for _, row in active_players_df.iterrows():
            p_id = row['id']
            name_label = player_map.get(p_id, "Unknown")
            p_num = int(row['Pairing']) if pd.notna(row['Pairing']) else "N/A"
            p_type = row['Type'] if pd.notna(row['Type']) else "Cutter"
            
            cloud_row = active_draft_df[active_draft_df['player_id'] == p_id]
            current_assignment = cloud_row['team_assigned'].values[0] if not cloud_row.empty else "Unassigned"
            idx = team_options.index(current_assignment) if current_assignment in team_options else 0
            
            col_lbl, col_sel = st.columns([3, 2])
            with col_lbl:
                st.markdown(f"**{name_label}** *(P{p_num} — {p_type})*")
            with col_sel:
                choice = st.selectbox(
                    "Assign", options=team_options, index=idx, key=f"sel_{p_id}", label_visibility="collapsed"
                )
                if choice != current_assignment:
                    supabase.table("active_draft").update({"team_assigned": choice}).eq("player_id", p_id).execute()
                    st.rerun()
                
        st.divider()
        
        st.subheader("Live Standings & Team Balances")
        team_cols = st.columns(num_teams)
        
        for i in range(num_teams):
            t_name = f"Team {i+1}"
            team_data = active_draft_df[active_draft_df['team_assigned'] == t_name].copy()
            
            team_data['pairing_val'] = team_data['player_id'].apply(get_pairing)
            team_data = team_data.sort_values(by=["display_order", "pairing_val"])
            
            final_order = team_data['player_id'].tolist()
            
            with team_cols[i]:
                t_score = sum([get_pairing(pid) if get_pairing(pid) != 99 else 15 for pid in final_order])
                st.markdown(f"### {t_name}")
                st.metric(label="Pairing Score", value=t_score)
                
                for idx, p_id in enumerate(final_order):
                    p_disp = player_map.get(p_id, "Unknown")
                    p_val = get_pairing(p_id)
                    p_str = f"P{p_val}" if p_val != 99 else "N/A"
                    
                    c1, c2, c3 = st.columns([6, 2, 2])
                    c1.write(f"**{p_disp}** *({p_str})*")
                    
                    if c2.button("🔼", key=f"up_{t_name}_{p_id}"):
                        if idx > 0:
                            above_p_id = final_order[idx-1]
                            supabase.table("active_draft").update({"display_order": idx}).eq("player_id", above_p_id).execute()
                            supabase.table("active_draft").update({"display_order": idx-1}).eq("player_id", p_id).execute()
                            st.rerun()
                            
                    if c3.button("🔽", key=f"dn_{t_name}_{p_id}"):
                        if idx < len(final_order) - 1:
                            below_p_id = final_order[idx+1]
                            supabase.table("active_draft").update({"display_order": idx}).eq("player_id", below_p_id).execute()
                            supabase.table("active_draft").update({"display_order": idx+1}).eq("player_id", p_id).execute()
                            st.rerun()

        st.divider()

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
                    for _, r in active_draft_df.iterrows():
                        if r['team_assigned'] != "Unassigned":
                            roster_batch.append({
                                "game_id": inserted_game_id,
                                "player_id": r['player_id'],
                                "team_assigned": r['team_assigned']
                            })
                    
                    if roster_batch:
                        supabase.table("game_rosters").insert(roster_batch).execute()
                        
                    supabase.table("active_draft").delete().neq("team_assigned", "FORCE_DELETE_ALL").execute()
                    
                    st.success("🎉 Match logged! Active board wiped for next game.")
                    st.balloons()
                    st.cache_data.clear()
                    st.rerun()
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
# TAB 4: ROSTER OVERVIEW & DISCOVERY CALCULATOR
# ==========================================
with tab_roster:
    st.header("Complete BAU League Roster")
    if df.empty:
        st.info("No records found.")
    else:
        df_display = df.copy()
        current_year = datetime.date.today().year
        
        # Pull history aggregates seamlessly using the cached pagination function
        try:
            lifetime_games, lifetime_days, current_year_days = get_roster_stats()
        except Exception as e:
            lifetime_games, lifetime_days, current_year_days = {}, {}, {}
        
        # Generate the new columns using safe mapping logic
        df_display[f'Days Played ({current_year})'] = df_display['id'].map(current_year_days).fillna(0).astype(int)
        df_display['Days Played (Lifetime)'] = df_display['id'].map(lifetime_days).fillna(0).astype(int)
        df_display['Games Played (Lifetime)'] = df_display['id'].map(lifetime_games).fillna(0).astype(int)
        
        df_display['Display Name'] = df['id'].map(player_map)
            
        if 'Date Joined' in df_display.columns:
            converted_dates = pd.to_datetime(df_display['Date Joined'], errors='coerce')
            today_date = datetime.date.today()
            df_display['Years in BAU'] = converted_dates.apply(
                lambda x: round((today_date - x.date()).days / 365.25, 0) if pd.notna(x) else 0.0
            )
            
            # Reorganize column structural presentation layouts
            cols = list(df_display.columns)
            cols.insert(0, cols.pop(cols.index('Display Name')))

            # Move stats to the end (after Notes)
            for stat_col in ['Years in BAU', f'Days Played ({current_year})', 'Days Played (Lifetime)', 'Games Played (Lifetime)']:
                if stat_col in cols:
                    cols.append(cols.pop(cols.index(stat_col)))
            
            if 'id' in cols: cols.remove('id')
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
        with col3: new_pairing = st.number_input("Pairing (1-30)", min_value=0, max_value=30, value=0)
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
                saved_name = f"{new_first} {new_last}".strip() if new_first else new_nick
                st.success(f"Added {saved_name}!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# ==========================================
# TAB 6: EDIT EXISTING PLAYER
# ==========================================
with tab_edit:
    st.header("✏️ Edit Player Database")
    
    if df.empty:
        st.info("No players available to edit.")
    else:
        # Safely sort the player options for the dropdown
        edit_sorted_ids = sorted(list(player_map.keys()), key=lambda x: player_map[x])
        
        # Player selector outside the form so it updates the default values dynamically
        selected_edit_id = st.selectbox(
            "Select Player to Edit", 
            options=edit_sorted_ids, 
            format_func=lambda x: player_map.get(x, "Unknown Player"),
            key="edit_player_selector"
        )
        
        # Extract the selected player's current data
        current_data = df[df['id'] == selected_edit_id].iloc[0]
        
        # Helper functions to handle empty/NaN data safely for Streamlit inputs
        def get_str(col): return str(current_data[col]).strip() if pd.notna(current_data.get(col)) else ""
        def get_bool(col): return bool(current_data[col]) if pd.notna(current_data.get(col)) else False
        def get_int(col): return int(current_data[col]) if pd.notna(current_data.get(col)) else 0
        
        with st.form("edit_player_form"):
            col1, col2 = st.columns(2)
            with col1: edit_first = st.text_input("First Name", value=get_str("First Name"))
            with col2: edit_last = st.text_input("Last Name", value=get_str("Last Name"))
            
            col_nick, col_stat = st.columns(2)
            with col_nick: edit_nick = st.text_input("Nickname", value=get_str("Nickname"))
            with col_stat:
                status_options = ["Regular", "Occasional", "Inactive"]
                curr_status = get_str("Status")
                stat_idx = status_options.index(curr_status) if curr_status in status_options else 0
                edit_status = st.selectbox("Status", status_options, index=stat_idx)
            
            col3, col4 = st.columns(2)
            with col3: edit_pairing = st.number_input("Pairing (1-30)", min_value=0, max_value=30, value=get_int("Pairing"))
            with col4: 
                pos_options = ["Cutter", "Handler", "Hybrid"]
                curr_pos = get_str("Type")
                pos_idx = pos_options.index(curr_pos) if curr_pos in pos_options else 0
                edit_type = st.selectbox("Position", pos_options, index=pos_idx)
            
            throw_options = ["Short", "Medium", "Long"]
            curr_throw = get_str("Throw")
            throw_idx = throw_options.index(curr_throw) if curr_throw in throw_options else 0
            edit_throw_range = st.selectbox("Throw Range", throw_options, index=throw_idx)
            
            st.write("**Player Traits:**")
            c1, c2 = st.columns(2)
            with c1:
                edit_both = st.checkbox("Both Throws", value=get_bool("Both Throws"))
                edit_coll = st.checkbox("Played College", value=get_bool("College"))
                edit_club = st.checkbox("Played Club", value=get_bool("Club"))
            with c2:
                edit_catch = st.checkbox("Consistent Catch", value=get_bool("Consistent Catch"))
                edit_dev = st.checkbox("Developing Player", value=get_bool("Developing"))
                edit_fast = st.checkbox("Fast / Speed", value=get_bool("Fast"))
                
            edit_notes = st.text_area("Notes", value=get_str("Notes"))
            
            st.divider()
            
            # The safety confirmation
            confirm_edit = st.checkbox("⚠️ I confirm I want to overwrite this player's data.")
            submit_edit = st.form_submit_button("Submit Edits to Database")
            
            if submit_edit:
                if not confirm_edit:
                    st.error("❌ Please check the confirmation box before submitting.")
                else:
                    payload = {
                        "Nickname": edit_nick if edit_nick else None, 
                        "First Name": edit_first, 
                        "Last Name": edit_last,
                        "Pairing": edit_pairing, "Type": edit_type, "Both Throws": edit_both,
                        "College": edit_coll, "Club": edit_club, "Consistent Catch": edit_catch,
                        "Developing": edit_dev, "Fast": edit_fast, "Throw": edit_throw_range,
                        "Notes": edit_notes, "Status": edit_status
                    }
                    
                    try:
                        supabase.table("players").update(payload).eq("id", selected_edit_id).execute()
                        st.success(f"🎉 Successfully updated {player_map.get(selected_edit_id)}!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating database: {e}")
