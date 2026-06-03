import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime

# ==========================================
# MOBILE-FIRST PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="BAU League",
    page_icon="🥏",
    layout="centered",        # centered works better than wide on phones
    initial_sidebar_state="collapsed"
)

# ==========================================
# MOBILE-FIRST CSS INJECTION
# ==========================================
st.markdown("""
<style>
/* === BASE MOBILE RESETS === */
html, body, [class*="css"] {
    font-size: 16px !important;   /* prevent iOS auto-zoom on inputs */
}

/* Reduce default Streamlit padding on mobile */
.block-container {
    padding: 0.75rem 0.75rem 2rem !important;
    max-width: 100% !important;
}

/* === TABS — larger touch targets === */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    flex-wrap: wrap;
}
.stTabs [data-baseweb="tab"] {
    padding: 10px 8px !important;
    font-size: 0.78rem !important;
    font-weight: 600;
    min-height: 44px;            /* Apple HIG minimum touch target */
}

/* === BUTTONS — bigger touch targets === */
.stButton > button {
    min-height: 48px !important;
    font-size: 1rem !important;
    border-radius: 10px !important;
    width: 100%;
}

/* Arrow buttons in draft board — large square touch targets */
button[kind="secondary"] {
    min-height: 44px !important;
    min-width: 44px !important;
    font-size: 1.2rem !important;
    padding: 4px !important;
}

/* === INPUTS — prevent iOS zoom (must be 16px+) === */
.stTextInput input,
.stNumberInput input,
.stSelectbox select,
.stTextArea textarea {
    font-size: 16px !important;
    min-height: 44px !important;
    border-radius: 8px !important;
}

/* === MULTISELECT — bigger chips === */
.stMultiSelect [data-baseweb="tag"] {
    font-size: 0.85rem !important;
    padding: 4px 8px !important;
}

/* === METRIC CARDS (team score display) === */
[data-testid="metric-container"] {
    background: #f0f4ff;
    border-radius: 12px;
    padding: 8px 12px !important;
    border: 1px solid #d0d8f0;
}

/* === EXPANDERS — bigger tap area === */
.streamlit-expanderHeader {
    font-size: 1rem !important;
    min-height: 48px !important;
    padding: 12px !important;
}

/* === PLAYER ROW CARDS in draft board === */
.player-card {
    background: #ffffff;
    border: 1px solid #e0e4ef;
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* === TEAM COLUMN CARDS === */
.team-card {
    background: #f7f9ff;
    border: 2px solid #c5d0f0;
    border-radius: 14px;
    padding: 10px;
    margin-bottom: 10px;
}

/* === SCORE BADGE === */
.score-badge {
    display: inline-block;
    background: #4361ee;
    color: white;
    font-weight: 700;
    font-size: 1.1rem;
    border-radius: 8px;
    padding: 2px 10px;
    margin-left: 6px;
}

/* === DIVIDER spacing === */
hr {
    margin: 0.75rem 0 !important;
}

/* Hide Streamlit branding on mobile to save space */
#MainMenu, footer { visibility: hidden; }

/* Slider touch target */
.stSlider [data-baseweb="slider"] {
    padding: 12px 0 !important;
}
.stSlider [role="slider"] {
    width: 28px !important;
    height: 28px !important;
}

/* Form submit button */
[data-testid="stFormSubmitButton"] > button {
    min-height: 52px !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    background: #4361ee !important;
    color: white !important;
    border: none !important;
}

/* Date input */
.stDateInput input {
    font-size: 16px !important;
    min-height: 44px !important;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# AUTHENTICATION & SECURITY LAYER
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    if st.session_state.authenticated:
        return True
    st.markdown("<h2 style='text-align:center; margin-top:2rem;'>🥏 BAU League</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#666; margin-bottom:1.5rem;'>Leader access only</p>", unsafe_allow_html=True)
    with st.form("Login Form"):
        password_input = st.text_input("Password", type="password", placeholder="Enter league password")
        submit_login = st.form_submit_button("Sign In →", use_container_width=True)
        if submit_login:
            if password_input == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect password.")
    return False

if not check_password():
    st.stop()

# ==========================================
# DATABASE CONNECTION
# ==========================================
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase: Client = init_connection()

@st.cache_data(ttl=30)
def load_players():
    response = supabase.table("players").select("*").execute()
    return pd.DataFrame(response.data)

df = load_players()

# Build ID → display name map
player_map = {}
if not df.empty:
    for _, row in df.iterrows():
        p_id = row.get('id')
        if pd.isna(p_id):
            continue
        fname = str(row.get('First Name', '')).strip() if pd.notna(row.get('First Name')) else ""
        lname = str(row.get('Last Name', '')).strip() if pd.notna(row.get('Last Name')) else ""
        nick  = str(row.get('Nickname', '')).strip() if pd.notna(row.get('Nickname')) else ""
        full  = f"{fname} {lname}".strip()
        player_map[p_id] = full if full else nick

def get_pairing(pid):
    if df.empty: return 99
    match = df[df['id'] == pid]['Pairing'].values
    return int(match[0]) if len(match) > 0 and pd.notna(match[0]) else 99

def get_cloud_draft():
    res = supabase.table("active_draft").select("*").execute()
    return pd.DataFrame(res.data)

active_draft_df = get_cloud_draft()
attendees_ids = active_draft_df['player_id'].tolist() if not active_draft_df.empty else []

# ==========================================
# HEADER
# ==========================================
st.markdown("## 🥏 BAU Hub")

# ==========================================
# TABS  (short labels save space on mobile)
# ==========================================
tab_lineup, tab_draft, tab_history, tab_roster, tab_add = st.tabs([
    "📋 Lineup",
    "🤝 Draft",
    "📜 History",
    "📊 Roster",
    "➕ Add"
])

# ==========================================
# TAB 1: ATTENDANCE / CHECK-IN
# ==========================================
with tab_lineup:
    st.subheader("Today's Check-In")
    st.caption("Tap players to mark them present. Save syncs to all devices.")

    sorted_ids = sorted(list(player_map.keys()), key=lambda x: player_map[x]) if player_map else []

    selected_attendees = st.multiselect(
        "Who's here today?",
        options=sorted_ids,
        default=attendees_ids,
        format_func=lambda x: player_map.get(x, "Unknown"),
        key="attendance_list_ids",
        placeholder="Search or tap to add players..."
    )

    st.markdown(f"**{len(selected_attendees)} players checked in**")

    if st.button("💾 Save & Sync Lineup", use_container_width=True):
        for p_id in selected_attendees:
            if p_id not in attendees_ids:
                supabase.table("active_draft").insert({"player_id": p_id, "team_assigned": "Unassigned"}).execute()
        for p_id in attendees_ids:
            if p_id not in selected_attendees:
                supabase.table("active_draft").delete().eq("player_id", p_id).execute()
        st.success("✅ Lineup synced!")
        st.rerun()

# ==========================================
# TAB 2: DRAFT BOARD  (mobile-first layout)
# ==========================================
with tab_draft:
    st.subheader("Team Draft")

    if not attendees_ids:
        st.warning("⚠️ Check in players on the Lineup tab first.")
    else:
        # Sync button at the top so it's easy to reach
        col_sync, col_teams = st.columns([1, 1])
        with col_sync:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        with col_teams:
            num_teams = st.selectbox("# Teams", [2, 3, 4], index=0, label_visibility="visible")

        team_options = ["Unassigned"] + [f"Team {i+1}" for i in range(num_teams)]

        # ---- AUTO-DRAFT ----
        st.divider()
        st.markdown("**⚡ Auto-Draft**")
        st.caption("Distributes players evenly by pairing number (snake draft order).")

        if st.button("🎲 Run Balanced Auto-Draft", use_container_width=True, type="primary"):
            present_players = df[df['id'].isin(attendees_ids)].copy()
            sorted_players  = present_players.sort_values(by="Pairing", ascending=True, na_position='last')
            direction = 1
            current_team_idx = 0
            for _, row in sorted_players.iterrows():
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
            st.success("✅ Auto-draft done!")
            st.rerun()

        # ---- MANUAL ASSIGN ----
        st.divider()
        st.markdown("**🔧 Adjust Assignments**")
        st.caption("Change any player's team with the dropdown.")

        active_players_df = df[df['id'].isin(attendees_ids)].copy()
        active_players_df['Display Name'] = active_players_df['id'].map(player_map)
        active_players_df = active_players_df.sort_values(by="Pairing", ascending=True, na_position='last')

        for _, row in active_players_df.iterrows():
            p_id   = row['id']
            name   = player_map.get(p_id, "Unknown")
            p_num  = int(row['Pairing']) if pd.notna(row.get('Pairing')) else None
            p_type = row['Type'] if pd.notna(row.get('Type')) else "?"
            p_str  = f"P{p_num}" if p_num is not None else "N/A"

            cloud_row  = active_draft_df[active_draft_df['player_id'] == p_id]
            current_t  = cloud_row['team_assigned'].values[0] if not cloud_row.empty else "Unassigned"
            idx        = team_options.index(current_t) if current_t in team_options else 0

            # Each player gets a compact card: name on top, dropdown below
            with st.container():
                st.markdown(
                    f"<div class='player-card'>"
                    f"<span style='font-weight:700'>{name}</span> "
                    f"<span style='color:#888; font-size:0.85rem'>· {p_str} · {p_type}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                choice = st.selectbox(
                    f"Team for {name}",
                    options=team_options,
                    index=idx,
                    key=f"sel_{p_id}",
                    label_visibility="collapsed"
                )
                if choice != current_t:
                    supabase.table("active_draft").update({"team_assigned": choice}).eq("player_id", p_id).execute()
                    st.rerun()

        # ---- TEAM VIEW (stacked on mobile, side-by-side via columns) ----
        st.divider()
        st.markdown("**📊 Team Breakdown**")
        st.caption("Tap ▲ ▼ to reorder players within a team.")

        # Reload fresh data before rendering teams
        active_draft_df = get_cloud_draft()

        # On mobile, 2 columns is readable; 3-4 teams stack into 2+2
        if num_teams == 2:
            team_col_layout = st.columns(2)
        elif num_teams == 3:
            team_col_layout = st.columns(3)
        else:
            # 4 teams: render as 2 rows of 2 for mobile readability
            team_col_layout = st.columns(2)

        for i in range(num_teams):
            t_name   = f"Team {i+1}"
            col_idx  = i if num_teams <= 3 else (i % 2)

            team_data   = active_draft_df[active_draft_df['team_assigned'] == t_name].copy()
            team_data['pairing_val'] = team_data['player_id'].apply(get_pairing)

            # Add display_order if missing
            if 'display_order' not in team_data.columns:
                team_data['display_order'] = range(len(team_data))
            team_data = team_data.sort_values(by=["display_order", "pairing_val"])
            final_order = team_data['player_id'].tolist()

            # Insert a blank row between team 1 and 2 for 4-team layout
            if num_teams == 4 and i == 2:
                st.markdown("")   # spacer before second row

            with team_col_layout[col_idx]:
                t_score = sum([get_pairing(pid) if get_pairing(pid) != 99 else 15 for pid in final_order])

                # Team header card
                st.markdown(
                    f"<div class='team-card'>"
                    f"<div style='font-weight:800; font-size:1rem; margin-bottom:4px;'>{t_name}</div>"
                    f"<div style='font-size:0.8rem; color:#555;'>Score: <strong>{t_score}</strong> · {len(final_order)} players</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

                for idx, p_id in enumerate(final_order):
                    p_disp = player_map.get(p_id, "Unknown")
                    p_val  = get_pairing(p_id)
                    p_str  = f"P{p_val}" if p_val != 99 else "?"

                    # Compact player row: name | ▲ | ▼
                    # Use 5:2:2 ratio so name has room, buttons are square
                    c_name, c_up, c_dn = st.columns([5, 1, 1])
                    with c_name:
                        st.markdown(
                            f"<div style='line-height:44px; font-size:0.88rem;'>"
                            f"<b>{p_disp}</b> <span style='color:#999'>·{p_str}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    with c_up:
                        if st.button("▲", key=f"up_{t_name}_{p_id}", help="Move up"):
                            if idx > 0:
                                above = final_order[idx - 1]
                                supabase.table("active_draft").update({"display_order": idx}).eq("player_id", above).execute()
                                supabase.table("active_draft").update({"display_order": idx - 1}).eq("player_id", p_id).execute()
                                st.rerun()
                    with c_dn:
                        if st.button("▼", key=f"dn_{t_name}_{p_id}", help="Move down"):
                            if idx < len(final_order) - 1:
                                below = final_order[idx + 1]
                                supabase.table("active_draft").update({"display_order": idx}).eq("player_id", below).execute()
                                supabase.table("active_draft").update({"display_order": idx + 1}).eq("player_id", p_id).execute()
                                st.rerun()

        # ---- LOG GAME RESULTS ----
        st.divider()
        st.markdown("**🏁 Log Match Results**")

        with st.form("save_game_form"):
            custom_game_date = st.date_input("Match Date", datetime.date.today())

            # Stack score inputs vertically on mobile (cleaner than columns)
            score_inputs = {}
            for i in range(num_teams):
                score_inputs[f"team_{i+1}_score"] = st.number_input(
                    f"Team {i+1} Final Score",
                    min_value=0, value=0, step=1,
                    key=f"score_t{i+1}"
                )

            submit_game = st.form_submit_button("✅ Submit & Save Results", use_container_width=True)

            if submit_game:
                game_payload = {
                    "game_date":   custom_game_date.strftime('%Y-%m-%d'),
                    "num_teams":   num_teams,
                    "team_1_score": score_inputs.get("team_1_score"),
                    "team_2_score": score_inputs.get("team_2_score"),
                    "team_3_score": score_inputs.get("team_3_score") if num_teams >= 3 else None,
                    "team_4_score": score_inputs.get("team_4_score") if num_teams == 4 else None,
                }
                try:
                    game_resp        = supabase.table("games").insert(game_payload).execute()
                    inserted_game_id = game_resp.data[0]['id']
                    roster_batch = []
                    for _, r in active_draft_df.iterrows():
                        if r['team_assigned'] != "Unassigned":
                            roster_batch.append({
                                "game_id":      inserted_game_id,
                                "player_id":    r['player_id'],
                                "team_assigned": r['team_assigned']
                            })
                    if roster_batch:
                        supabase.table("game_rosters").insert(roster_batch).execute()
                    supabase.table("active_draft").delete().neq("team_assigned", "FORCE_DELETE_ALL").execute()
                    st.success("🎉 Match logged! Board cleared for next game.")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# ==========================================
# TAB 3: GAME HISTORY
# ==========================================
with tab_history:
    st.subheader("Game History")
    try:
        games_fetch      = supabase.table("games").select("*").order("game_date", desc=True).execute()
        historical_games = games_fetch.data

        if not historical_games:
            st.info("No saved games yet.")
        else:
            for gm in historical_games:
                g_id   = gm['id']
                g_date = gm['game_date']

                # Build a compact score line
                scores = []
                for i in range(1, gm['num_teams'] + 1):
                    s = gm.get(f'team_{i}_score')
                    scores.append(f"T{i}:{s}" if s is not None else f"T{i}:—")
                score_line = "  ·  ".join(scores)

                with st.expander(f"📅 {g_date}  |  {score_line}"):
                    st.markdown(f"**{gm['num_teams']} teams** · Scores: `{score_line}`")

                    roster_fetch = supabase.table("game_rosters").select("*").eq("game_id", g_id).execute()
                    rost_df      = pd.DataFrame(roster_fetch.data)

                    if not rost_df.empty:
                        # Show teams side-by-side even in history
                        unique_teams = sorted(rost_df['team_assigned'].unique())
                        h_cols = st.columns(len(unique_teams)) if len(unique_teams) <= 3 else st.columns(2)
                        for ti, team_lbl in enumerate(unique_teams):
                            col_i = ti if len(unique_teams) <= 3 else ti % 2
                            with h_cols[col_i]:
                                st.markdown(f"**{team_lbl}**")
                                p_ids  = rost_df[rost_df['team_assigned'] == team_lbl]['player_id'].tolist()
                                p_list = sorted([player_map.get(pid, "Unknown") for pid in p_ids])
                                for name in p_list:
                                    st.markdown(f"<div style='font-size:0.88rem; padding:2px 0;'>· {name}</div>", unsafe_allow_html=True)
                    else:
                        st.caption("No roster data for this match.")
    except Exception as e:
        st.error(f"Failed to load history: {e}")

# ==========================================
# TAB 4: ROSTER OVERVIEW
# ==========================================
with tab_roster:
    st.subheader("Full Roster")
    if df.empty:
        st.info("No players found.")
    else:
        df_display   = df.copy()
        current_year = datetime.date.today().year

        try:
            g_resp  = supabase.table("games").select("id", "game_date").execute()
            gr_resp = supabase.table("game_rosters").select("game_id", "player_id").execute()
            games_df   = pd.DataFrame(g_resp.data)
            rosters_df = pd.DataFrame(gr_resp.data)

            if not games_df.empty and not rosters_df.empty:
                history_merged = rosters_df.merge(games_df, left_on="game_id", right_on="id")
                history_merged['game_date'] = pd.to_datetime(history_merged['game_date'], errors='coerce')

                lifetime_games    = history_merged.groupby('player_id').size().to_dict()
                lifetime_days     = history_merged.groupby('player_id')['game_date'].nunique().to_dict()
                current_year_df   = history_merged[history_merged['game_date'].dt.year == current_year]
                current_year_days = current_year_df.groupby('player_id')['game_date'].nunique().to_dict()
            else:
                lifetime_games = lifetime_days = current_year_days = {}
        except Exception:
            lifetime_games = lifetime_days = current_year_days = {}

        df_display[f'Days ({current_year})']  = df_display['id'].map(current_year_days).fillna(0).astype(int)
        df_display['Days (All Time)']          = df_display['id'].map(lifetime_days).fillna(0).astype(int)
        df_display['Games (All Time)']         = df_display['id'].map(lifetime_games).fillna(0).astype(int)
        df_display['Display Name']             = df['id'].map(player_map)

        if 'Date Joined' in df_display.columns:
            converted_dates = pd.to_datetime(df_display['Date Joined'], errors='coerce')
            today_date      = datetime.date.today()
            df_display['Years in BAU'] = converted_dates.apply(
                lambda x: round((today_date - x.date()).days / 365.25, 0) if pd.notna(x) else 0.0
            )

        # --- Column ordering: Display Name first, stats after Notes ---
        base_cols = ['Display Name', 'Pairing', 'Type', 'Throw', 'Both Throws',
                     'College', 'Club', 'Consistent Catch', 'Developing',
                     'Endurance', 'Fast', 'Notes', 'Status', 'Date Joined']

        stat_cols = ['Years in BAU', f'Days ({current_year})', 'Days (All Time)', 'Games (All Time)']

        available_base = [c for c in base_cols if c in df_display.columns]
        available_stat = [c for c in stat_cols if c in df_display.columns]
        final_cols     = available_base + available_stat

        df_display = df_display[final_cols]

        # Mobile-friendly: add a search filter above the table
        search = st.text_input("🔍 Search player", placeholder="Type a name...")
        if search:
            df_display = df_display[df_display['Display Name'].str.contains(search, case=False, na=False)]

        st.dataframe(
            df_display.sort_values(by="Display Name"),
            hide_index=True,
            use_container_width=True,
            height=500
        )

# ==========================================
# TAB 5: ADD PLAYER
# ==========================================
with tab_add:
    st.subheader("Add New Player")
    with st.form("add_player_form", clear_on_submit=True):
        new_first = st.text_input("First Name", placeholder="First")
        new_last  = st.text_input("Last Name",  placeholder="Last")
        new_nick  = st.text_input("Nickname (optional)")

        col3, col4 = st.columns(2)
        with col3:
            new_pairing = st.number_input("Pairing (1–30)", min_value=1, max_value=30, value=15)
        with col4:
            new_type = st.selectbox("Position", ["Cutter", "Handler", "Hybrid"])

        new_throw = st.selectbox("Throw Range", ["Short", "Medium", "Long"])
        new_status = st.selectbox("Status", ["Regular", "Occasional", "Inactive"])

        st.markdown("**Traits**")
        # 3-column trait grid is touch-friendly
        t1, t2, t3 = st.columns(3)
        with t1:
            feat_both  = st.checkbox("Both Throws")
            feat_catch = st.checkbox("Consistent Catch")
        with t2:
            feat_coll  = st.checkbox("College")
            feat_dev   = st.checkbox("Developing")
        with t3:
            feat_club  = st.checkbox("Club")
            feat_fast  = st.checkbox("Fast")

        new_notes = st.text_area("Notes", placeholder="Any notes about this player...")

        submitted = st.form_submit_button("➕ Add Player", use_container_width=True)

        if submitted:
            if not new_first and not new_nick:
                st.error("Please enter at least a first name or nickname.")
            else:
                payload = {
                    "Nickname": new_nick.strip() if new_nick else None,
                    "First Name": new_first.strip(),
                    "Last Name":  new_last.strip(),
                    "Pairing":    new_pairing,
                    "Type":       new_type,
                    "Both Throws": feat_both,
                    "College":    feat_coll,
                    "Club":       feat_club,
                    "Consistent Catch": feat_catch,
                    "Developing": feat_dev,
                    "Fast":       feat_fast,
                    "Throw":      new_throw,
                    "Notes":      new_notes.strip(),
                    "Date Joined": datetime.date.today().strftime('%m/%d/%Y'),
                    "Status":     new_status,
                }
                try:
                    supabase.table("players").insert(payload).execute()
                    saved_name = f"{new_first} {new_last}".strip() if new_first else new_nick
                    st.success(f"✅ Added {saved_name}!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
