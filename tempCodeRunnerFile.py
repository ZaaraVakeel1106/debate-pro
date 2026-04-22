from flask import Flask, render_template, request, redirect, session
from models import *

app = Flask(__name__)
app.secret_key = "secret123"


# ---------------- INIT DB ----------------
def init_db():

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        username TEXT,
        password TEXT,
        role TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS teams(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS rounds(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        motion TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS matches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1 INTEGER,
        team2 INTEGER,
        round_id INTEGER,
        score1 INTEGER DEFAULT 0,
        score2 INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        winner_team INTEGER
    )
    """)

    conn.commit()


# ---------------- DEFAULT ADMIN ----------------
def create_default_user():
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES ('admin','admin','admin')")
        conn.commit()


# ---------------- HOME ----------------
@app.route('/')
def home():
    return render_template('home.html')


# ---------------- LOGIN ----------------
@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    user = authenticate(request.form['username'], request.form['password'])

    if user:
        session['user'] = user
        return redirect('/dashboard')

    return "Invalid Login"


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():

    teams = get_teams()
    rounds = get_rounds()
    matches = get_matches()

    try:
        stats = get_stats()
    except:
        stats = {
            "teams": len(teams),
            "matches": len(matches),
            "completed": 0
        }

    return render_template(
        'dashboard.html',
        teams=teams,
        rounds=rounds,
        matches=matches,
        stats=stats
    )


# ---------------- ADMIN ----------------
@app.route('/admin')
def admin():

    users = get_users()
    teams = get_teams()
    rounds = get_rounds()

    return render_template('admin.html', users=users, teams=teams, rounds=rounds)


# ---------------- ADD USER ----------------
@app.route('/add_user', methods=['POST'])
def add_user_route():
    add_user(
        request.form['username'],
        request.form['password'],
        request.form['role']
    )
    return redirect('/admin')


# ---------------- ADD TEAM ----------------
@app.route('/add_team', methods=['POST'])
def add_team_route():
    add_team(request.form['team'])
    return redirect('/admin')


# ---------------- GENERATE MATCHES ----------------
@app.route('/generate_matches', methods=['POST'])
def gen():

    teams = get_teams()

    if len(teams) < 2:
        return redirect('/admin')

    # prevent duplicate tournament
    c.execute("SELECT COUNT(*) FROM rounds")
    if c.fetchone()[0] > 0:
        return redirect('/judge')

    round_name = request.form.get("round_name", "Round 1")
    motion = request.form.get("motion", "No Motion")

    c.execute("INSERT INTO rounds (name, motion) VALUES (?,?)",
              (round_name, motion))

    round_id = c.lastrowid

    generate_matches(round_id)

    return redirect('/judge')


# ---------------- JUDGE ----------------
@app.route('/judge')
def judge():

    current_round = get_current_round()

    if not current_round:
        return render_template(
            'judge.html',
            matches=[],
            current_round="No Round",
            pending_exists=False
        )

    matches = get_matches_by_round(current_round)

    pending_exists = any(m[7] == 'pending' for m in matches)

    return render_template(
        'judge.html',
        matches=matches,
        current_round=current_round,
        pending_exists=pending_exists
    )


# ---------------- SUBMIT SCORE ----------------
@app.route('/submit_score', methods=['POST'])
def submit_score():

    match_ids = request.form.getlist('match_id[]')

    content1 = request.form.getlist('content1[]')
    delivery1 = request.form.getlist('delivery1[]')
    rebuttal1 = request.form.getlist('rebuttal1[]')

    content2 = request.form.getlist('content2[]')
    delivery2 = request.form.getlist('delivery2[]')
    rebuttal2 = request.form.getlist('rebuttal2[]')

    submit_scores(
        match_ids,
        content1, delivery1, rebuttal1,
        content2, delivery2, rebuttal2
    )

    last_round = get_last_round_id()

    c.execute("""
    SELECT COUNT(*) FROM matches 
    WHERE status='pending' AND round_id=?
    """, (last_round,))

    pending = c.fetchone()[0]

    if pending == 0:

        winners = get_winners(last_round)

        if len(winners) > 1:
            return redirect('/next_round_setup')
        else:
            return redirect('/leaderboard')

    return redirect('/judge')


# ---------------- NEXT ROUND ----------------
@app.route('/next_round_setup')
def next_round_setup():
    return render_template('next_round.html')


@app.route('/create_next_round', methods=['POST'])
def create_next_round():

    motion = request.form.get('motion', 'No Motion')

    generate_next_round(motion)

    return redirect('/judge')


# ---------------- DELETE TEAM ----------------
@app.route('/delete_team/<int:id>')
def delete_team_route(id):
    c.execute("DELETE FROM teams WHERE id=?", (id,))
    conn.commit()
    return redirect('/admin')


# ---------------- RESET ----------------
@app.route('/reset_tournament')
def reset():

    c.execute("DELETE FROM matches")
    c.execute("DELETE FROM rounds")
    conn.commit()

    return redirect('/admin')


# ---------------- LEADERBOARD ----------------
@app.route('/leaderboard')
def lb():

    data = advanced_leaderboard()

    try:
        winner = get_final_winner()
    except:
        winner = None

    return render_template(
        'leaderboard.html',
        data=data,
        winner=winner
    )


# ---------------- BRACKET ----------------
@app.route('/bracket')
def bracket():
    data = get_bracket_data()

    final_winner = None
    if data:
        last_round = data[-1]
        if last_round:
            final_winner = last_round[-1]["winner"]

    return render_template(
        'bracket.html',
        bracket=data,
        final_winner=final_winner
    )


# ---------------- DEBUG ----------------
@app.route('/debug_matches')
def debug_matches():
    c.execute("SELECT id, team1, team2, status FROM matches")
    return str(c.fetchall())


# ---------------- RUN ----------------
import webbrowser

if __name__ == '__main__':
    init_db()
    create_default_user()

    webbrowser.open("http://127.0.0.1:5000/")
    app.run(debug=True)