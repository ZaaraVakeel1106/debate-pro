import sqlite3
import random

conn = sqlite3.connect('database.db', check_same_thread=False)
c = conn.cursor()


# ---------------- USERS ----------------
def add_user(username, password, role):
    c.execute("INSERT INTO users VALUES (?,?,?)", (username, password, role))
    conn.commit()

def get_users():
    c.execute("SELECT * FROM users")
    return c.fetchall()

def authenticate(username, password):
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    return c.fetchone()


# ---------------- TEAMS ----------------
def add_team(name):
    c.execute("INSERT INTO teams (name) VALUES (?)", (name,))
    conn.commit()

def get_teams():
    c.execute("SELECT * FROM teams")
    return c.fetchall()


# ---------------- ROUNDS ----------------
def add_round(name, motion):
    c.execute("INSERT INTO rounds (name, motion) VALUES (?,?)", (name, motion))
    conn.commit()

def get_round():
    c.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1")
    return c.fetchone()

def get_rounds():
    c.execute("SELECT * FROM rounds")
    return c.fetchall()


# ---------------- MATCHES ----------------
def generate_matches(round_id):

    teams = get_teams()

    if len(teams) < 2:
        return

    team_ids = [t[0] for t in teams]

    import random
    random.shuffle(team_ids)

    # 🔥 HANDLE BYE PROPERLY
    if len(team_ids) % 2 != 0:
        bye_team = team_ids.pop()

        c.execute("""
        INSERT INTO matches (team1, team2, round_id, score1, score2, status, winner_team)
        VALUES (?,?,?,?,?,?,?)
        """, (bye_team, None, round_id, 0, 0, 'completed', bye_team))

    # 🔥 CREATE MATCHES
    for i in range(0, len(team_ids), 2):
        t1 = team_ids[i]
        t2 = team_ids[i+1]

        c.execute("""
        INSERT INTO matches (team1, team2, round_id, score1, score2, status)
        VALUES (?,?,?,0,0,'pending')
        """, (t1, t2, round_id))

    conn.commit()


# ---------------- GET MATCHES ----------------
def get_matches():
    current_round_id = get_last_round_id()

    c.execute("""
    SELECT m.id, 
           COALESCE(t1.name, 'BYE'),
           COALESCE(t2.name, 'BYE'),
           r.name, 
           r.motion,
           m.score1, 
           m.score2,
           m.status
    FROM matches m
    LEFT JOIN teams t1 ON m.team1 = t1.id
    LEFT JOIN teams t2 ON m.team2 = t2.id
    LEFT JOIN rounds r ON m.round_id = r.id
    WHERE m.round_id = ?
    ORDER BY m.id DESC
    """, (current_round_id,))

    return c.fetchall()


# ---------------- SCORING ----------------
def submit_scores(ids, c1, d1, r1, c2, d2, r2):

    score_index = 0  # separate index for score arrays

    for i in range(len(ids)):

        # GET MATCH
        c.execute("SELECT team1, team2 FROM matches WHERE id=?", (ids[i],))
        match = c.fetchone()

        if not match:
            continue

        t1, t2 = match

        # 🚫 SKIP BYE MATCHES
        if t1 is None or t2 is None:
            continue

        # 🚫 CHECK INDEX SAFE
        if score_index >= len(c1):
            continue

        # 🚫 SKIP EMPTY INPUT
        if not c1[score_index] or not d1[score_index] or not r1[score_index] \
        or not c2[score_index] or not d2[score_index] or not r2[score_index]:
            score_index += 1
            continue

        s1 = int(c1[score_index]) + int(d1[score_index]) + int(r1[score_index])
        s2 = int(c2[score_index]) + int(d2[score_index]) + int(r2[score_index])

        winner = t1 if s1 > s2 else t2

        c.execute("""
        UPDATE matches
        SET score1=?, score2=?, status='completed', winner_team=?
        WHERE id=?
        """, (s1, s2, winner, ids[i]))

        score_index += 1

    conn.commit()

# ---------------- STATS ----------------
def get_stats():

    c.execute("SELECT COUNT(*) FROM teams")
    teams = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM matches")
    matches = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM matches WHERE status='completed'")
    completed = c.fetchone()[0]

    return {
        "teams": teams,
        "matches": matches,
        "completed": completed
    }


# ---------------- LEADERBOARD ----------------
def leaderboard():
    c.execute("""
    SELECT t.name,
           COALESCE(SUM(
                CASE 
                    WHEN t.id = m.team1 THEN m.score1
                    WHEN t.id = m.team2 THEN m.score2
                END
           ),0) as total_score
    FROM teams t
    LEFT JOIN matches m
    ON t.id = m.team1 OR t.id = m.team2
    GROUP BY t.id
    ORDER BY total_score DESC
    """)
    return c.fetchall()


def advanced_leaderboard():
    c.execute("""
    SELECT t.name,
           SUM(CASE WHEN m.winner_team = t.id THEN 1 ELSE 0 END) as wins,
           COALESCE(SUM(
                CASE 
                    WHEN t.id = m.team1 THEN m.score1
                    WHEN t.id = m.team2 THEN m.score2
                END
           ),0) as total_score
    FROM teams t
    LEFT JOIN matches m
    ON t.id = m.team1 OR t.id = m.team2
    GROUP BY t.id
    ORDER BY wins DESC, total_score DESC
    """)
    return c.fetchall()


# ---------------- HELPERS ----------------
def get_last_round_id():
    c.execute("SELECT MAX(id) FROM rounds")
    result = c.fetchone()[0]
    return result 


def get_winners(round_id):

    c.execute("""
    SELECT winner_team 
    FROM matches 
    WHERE round_id=? AND status='completed'
    """, (round_id,))

    winners = [row[0] for row in c.fetchall() if row[0] is not None]

    return winners


def get_least_bye_team(team_ids):

    bye_count = {}

    for t in team_ids:
        c.execute("""
        SELECT COUNT(*) FROM matches 
        WHERE (team1=? OR team2=?) AND team2 IS NULL
        """, (t, t))

        bye_count[t] = c.fetchone()[0]

    return min(bye_count, key=bye_count.get)


# ---------------- AUTO NEXT ROUND ----------------
def generate_next_round(motion="Auto Generated Motion"):

    last_round = get_last_round_id()
    if not last_round:
        return

    winners = get_winners(last_round)

    # 🛑 STOP if tournament finished
    if len(winners) <= 1:
        return

    # ✅ CREATE NEW ROUND
    round_name = f"Round {last_round + 1}"
    c.execute("INSERT INTO rounds (name, motion) VALUES (?,?)", (round_name, motion))
    new_round_id = c.lastrowid

    # -------------------------
    # 🧠 STEP 1: GET TEAM WINS
    # -------------------------
    c.execute("""
    SELECT t.id, COUNT(m.winner_team) as wins
    FROM teams t
    LEFT JOIN matches m ON t.id = m.winner_team
    GROUP BY t.id
    """)

    team_data = c.fetchall()  # [(team_id, wins)]

    # -------------------------
    # 🧠 STEP 2: SORT BY WINS
    # -------------------------
    sorted_teams = sorted(team_data, key=lambda x: x[1], reverse=True)

    team_ids = [t[0] for t in sorted_teams if t[0] in winners]

    # -------------------------
    # 🧠 STEP 3: HANDLE BYE
    # -------------------------
    if len(team_ids) % 2 != 0:
        bye_team = get_least_bye_team(team_ids)
        team_ids.remove(bye_team)

        c.execute("""
        INSERT INTO matches (team1, team2, round_id, score1, score2, status, winner_team)
        VALUES (?,?,?,?,?,?,?)
        """, (bye_team, None, new_round_id, 10, 0, 'completed', bye_team))

    # -------------------------
    # 🧠 STEP 4: PAIRING
    # -------------------------
    used = set()

    for i in range(len(team_ids)):
        if team_ids[i] in used:
            continue

        for j in range(i+1, len(team_ids)):
            if team_ids[j] in used:
                continue

            t1 = team_ids[i]
            t2 = team_ids[j]

            # ❌ avoid repeat matches
            c.execute("""
            SELECT COUNT(*) FROM matches 
            WHERE (team1=? AND team2=?) OR (team1=? AND team2=?)
            """, (t1, t2, t2, t1))

            if c.fetchone()[0] == 0:
                c.execute("""
                INSERT INTO matches (team1, team2, round_id, status)
                VALUES (?,?,?, 'pending')
                """, (t1, t2, new_round_id))

                used.add(t1)
                used.add(t2)
                break

    conn.commit()
def get_current_round():
    c.execute("SELECT id FROM rounds ORDER BY id DESC LIMIT 1")
    r = c.fetchone()
    return r[0] if r else None

def get_final_winner():

    c.execute("""
    SELECT t.name
    FROM teams t
    LEFT JOIN matches m ON t.id = m.winner_team
    GROUP BY t.id
    ORDER BY COUNT(m.winner_team) DESC
    LIMIT 1
    """)

    result = c.fetchone()

    return result[0] if result else None
def get_matches_by_round(round_id):
    c.execute("""
    SELECT m.id, 
           COALESCE(t1.name, 'BYE'),
           COALESCE(t2.name, 'BYE'),
           r.name, 
           r.motion,
           m.score1, 
           m.score2,
           m.status
    FROM matches m
    LEFT JOIN teams t1 ON m.team1 = t1.id
    LEFT JOIN teams t2 ON m.team2 = t2.id
    LEFT JOIN rounds r ON m.round_id = r.id
    WHERE m.round_id = ?
    ORDER BY m.id DESC
    """, (round_id,))
    return c.fetchall()
def get_bracket_data():
    c.execute("""
    SELECT r.id, r.name,
           t1.name, t2.name,
           m.winner_team
    FROM matches m
    LEFT JOIN teams t1 ON m.team1 = t1.id
    LEFT JOIN teams t2 ON m.team2 = t2.id
    LEFT JOIN rounds r ON m.round_id = r.id
    ORDER BY r.id, m.id
    """)

    rows = c.fetchall()

    bracket = []
    current_round = None
    round_data = []

    for r_id, r_name, t1, t2, winner in rows:

        if current_round != r_name:
            if round_data:
                bracket.append(round_data)
            round_data = []
            current_round = r_name

        # ✅ FIX: winner id → name
        winner_name = None
        if winner:
            c.execute("SELECT name FROM teams WHERE id=?", (winner,))
            res = c.fetchone()
            if res:
                winner_name = res[0]

        round_data.append({
            "team1": t1 or "BYE",
            "team2": t2 or "BYE",
            "winner": winner_name
        })

    if round_data:
        bracket.append(round_data)

    return bracket