from __future__ import annotations

import atexit
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger("preceptron")
logging.basicConfig(level=logging.INFO)

BACKEND_DIR = Path(__file__).resolve().parent
BASE_DIR = BACKEND_DIR.parent
DATA_DIR = BASE_DIR / "data" if (BASE_DIR / "data").parent.exists() else BACKEND_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "preceptron.db"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = bool(DATABASE_URL)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes"}

app = FastAPI(title="Preceptron API", version="2.0.0")

# CORS Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip()
# Always allow the known production origin so cross-origin cookies work even
# if the FRONTEND_URL env var is not set on Render.
_PRODUCTION_ORIGIN = "https://perceptron-texd.onrender.com"
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    _PRODUCTION_ORIGIN,
]
if FRONTEND_URL:
    for origin in FRONTEND_URL.split(","):
        cleaned = origin.strip().rstrip("/")
        if cleaned and cleaned not in allowed_origins:
            allowed_origins.append(cleaned)
logger.info("CORS allowed_origins: %s", allowed_origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Database layer (SQLite / Neon PostgreSQL) -----------------

class Row(dict):
    """Universal Row object supporting column name lookup, positional index, and dict conversion."""
    def __init__(self, keys, values):
        super().__init__(zip(keys, values))
        self._values = list(values)

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        return super().__getitem__(item)


def pg_row_factory(cursor):
    if cursor.description is None:
        try:
            from psycopg.rows import no_result
            return no_result
        except Exception:
            return None
    titles = [c.name for c in cursor.description]
    def make_row(values):
        return Row(titles, values)
    return make_row


_pg_pool = None


def _cleanup_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        try:
            _pg_pool.close()
        except Exception:
            pass
        _pg_pool = None


atexit.register(_cleanup_pg_pool)


def get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import psycopg_pool
        _pg_pool = psycopg_pool.ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            open=True,
            check=psycopg_pool.ConnectionPool.check_connection,
        )
    return _pg_pool


class CursorWrapper:
    def __init__(self, is_pg: bool, raw_cursor):
        self.is_pg = is_pg
        self.raw_cursor = raw_cursor

    def fetchone(self):
        if self.is_pg and getattr(self.raw_cursor, "description", None) is None:
            return None
        return self.raw_cursor.fetchone()

    def fetchall(self):
        if self.is_pg and getattr(self.raw_cursor, "description", None) is None:
            return []
        return self.raw_cursor.fetchall()


class DBWrapper:
    def __init__(self, is_pg: bool, conn):
        self.is_pg = is_pg
        self.conn = conn

    def _convert_sql(self, sql: str) -> str:
        if self.is_pg:
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params: tuple | list = ()):
        c_sql = self._convert_sql(sql)
        cur = self.conn.cursor()
        cur.execute(c_sql, params)
        return CursorWrapper(self.is_pg, cur)

    def executemany(self, sql: str, seq_of_params):
        c_sql = self._convert_sql(sql)
        cur = self.conn.cursor()
        cur.executemany(c_sql, seq_of_params)
        return CursorWrapper(self.is_pg, cur)

    def executescript(self, script: str):
        if self.is_pg:
            cur = self.conn.cursor()
            cur.execute(script)
        else:
            self.conn.executescript(script)


@contextmanager
def db():
    if IS_POSTGRES:
        pool = get_pg_pool()
        with pool.connection() as conn:
            conn.row_factory = pg_row_factory
            with conn.transaction():
                yield DBWrapper(True, conn)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield DBWrapper(False, conn)
        finally:
            conn.close()


SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, role TEXT NOT NULL, profile_complete INTEGER DEFAULT 1,
        college TEXT DEFAULT '', branch TEXT DEFAULT 'CSE', graduation_year INTEGER DEFAULT 2027,
        target_role TEXT DEFAULT 'Software Engineer'
    )""",
    """CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tasks(
        id TEXT PRIMARY KEY, title TEXT, category TEXT, difficulty TEXT,
        estimated_minutes INTEGER, status TEXT, date TEXT, details TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS resume_analyses(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT, role TEXT, score INTEGER,
        payload TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS assessment_attempts(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, question_id TEXT NOT NULL, selected_index INTEGER,
        correct INTEGER NOT NULL, category TEXT NOT NULL, topic TEXT NOT NULL, difficulty TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS practice_attempts(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, question_id TEXT NOT NULL, selected_index INTEGER,
        correct INTEGER NOT NULL, category TEXT NOT NULL, topic TEXT NOT NULL, difficulty TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
]


def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return f"pbkdf2_sha256${salt}${hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if stored_hash == password:
        return True
    if not stored_hash.startswith("pbkdf2_sha256$"):
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 3:
            return False
        _, salt, expected_hash = parts
        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        ).hex()
        return hmac.compare_digest(candidate_hash, expected_hash)
    except Exception:
        return False


def seed_demo_users(c):
    # 1. Demo student
    student_email = "student@demo.com"
    student_row = c.execute("SELECT * FROM users WHERE email=?", (student_email,)).fetchone()
    if not student_row:
        c.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)", (
            "student-001", "Demo Student", student_email, hash_password("demo123"), "student", 1,
            "Northstar Institute of Technology", "CSE", 2027, "Software Engineer"
        ))
    else:
        needs_fix = False
        stored_pw = student_row["password"] or ""
        if not stored_pw.startswith("pbkdf2_sha256$") or not verify_password("demo123", stored_pw):
            needs_fix = True
        if student_row["role"] != "student":
            needs_fix = True
        if needs_fix:
            c.execute(
                "UPDATE users SET password=?, role=?, name=? WHERE email=?",
                (hash_password("demo123"), "student", "Demo Student", student_email)
            )
    logger.info("Demo student account ready")

    # 2. Demo TPO
    tpo_email = "tpo@demo.com"
    tpo_row = c.execute("SELECT * FROM users WHERE email=?", (tpo_email,)).fetchone()
    if not tpo_row:
        c.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)", (
            "tpo-001", "Placement Officer", tpo_email, hash_password("demo123"), "tpo", 1,
            "Northstar Institute of Technology", "", 2027, "Software Engineer"
        ))
    else:
        needs_fix = False
        stored_pw = tpo_row["password"] or ""
        if not stored_pw.startswith("pbkdf2_sha256$") or not verify_password("demo123", stored_pw):
            needs_fix = True
        if tpo_row["role"] != "tpo":
            needs_fix = True
        if needs_fix:
            c.execute(
                "UPDATE users SET password=?, role=?, name=? WHERE email=?",
                (hash_password("demo123"), "tpo", "Placement Officer", tpo_email)
            )
    logger.info("Demo TPO account ready")


def init_db():
    if IS_POSTGRES:
        safe_host = re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", DATABASE_URL).split("@")[-1]
        logger.info("Initializing PostgreSQL schema at %s", safe_host)
    else:
        logger.info("Initializing SQLite database at %s", DB_PATH)

    with db() as c:
        for stmt in SCHEMA_STATEMENTS:
            c.execute(stmt)
        seed_demo_users(c)
        task_count = c.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()
        if (task_count["c"] if task_count else 0) == 0:
            tasks = [
                ("r1", "Binary Search: Peak Element II", "DSA", "Medium", 35, "todo", "Today", "Solve a 2D peak-element problem and explain the O(m log n) approach."),
                ("r2", "SQL Joins Sprint", "SQL", "Easy", 25, "todo", "Today", "Practice INNER, LEFT and self joins on placement-style datasets."),
                ("r3", "Explain Your Project", "Communication", "Medium", 20, "done", "Today", "Give a 90-second STAR-style project explanation."),
                ("r4", "Operating Systems Revision", "Core CS", "Medium", 30, "todo", "Tomorrow", "Revise processes, threads, scheduling and deadlocks."),
                ("r5", "Hashing Interview Drill", "DSA", "Easy", 25, "todo", "Tomorrow", "Solve frequency-map and two-sum variants without looking at hints."),
            ]
            c.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", tasks)



_db_initialized = False

try:
    init_db()
    _db_initialized = True
except Exception as _init_exc:
    logger.error("[STARTUP] init_db() failed at module load: %s", _init_exc)
    logger.error("[STARTUP] Will retry init_db() on first request via startup event.")


@app.on_event("startup")
async def startup_event():
    global _db_initialized
    if not _db_initialized:
        logger.info("[STARTUP] Retrying init_db() in startup event …")
        try:
            init_db()
            _db_initialized = True
            logger.info("[STARTUP] init_db() succeeded on retry.")
        except Exception as exc:
            logger.error("[STARTUP] init_db() retry failed: %s", exc)
    else:
        logger.info("[STARTUP] DB already initialized.")

SKILLS = [
    {"category": "DSA", "score": 68, "label": "Developing"},
    {"category": "Core CS", "score": 74, "label": "Strong"},
    {"category": "Problem Solving", "score": 61, "label": "Developing"},
    {"category": "Communication", "score": 82, "label": "Strong"},
    {"category": "SQL", "score": 55, "label": "Needs focus"},
]
QUESTIONS = [
    # DSA
    {"id":"dsa1","category":"DSA","topic":"Binary Search","question":"In a sorted array, which strategy gives O(log n) search time?","options":["Linear scan","Binary search","Two nested loops","Bubble sort"],"difficulty":"Easy","correct_index":1,"explanation":"Binary search halves the remaining search space after each comparison."},
    {"id":"dsa2","category":"DSA","topic":"Binary Search","question":"What is the first step when implementing binary search on indices l and r?","options":["Set mid = l + (r-l)/2","Sort again","Move l to r","Use a stack"],"difficulty":"Easy","correct_index":0,"explanation":"The midpoint is chosen without risking integer overflow from (l+r)/2."},
    {"id":"dsa3","category":"DSA","topic":"Arrays","question":"What is the average-time lookup complexity of a hash table with a good hash function?","options":["O(1)","O(log n)","O(n)","O(n log n)"],"difficulty":"Easy","correct_index":0,"explanation":"Hash-table lookup is expected O(1) on average, assuming good hashing and controlled load."},
    {"id":"dsa4","category":"DSA","topic":"Two Pointers","question":"Which pattern is especially useful for finding a pair with a target sum in a sorted array?","options":["Two pointers","DFS only","Heap sort","Prefix tree"],"difficulty":"Easy","correct_index":0,"explanation":"Place pointers at both ends and move them based on whether the sum is too small or too large."},
    {"id":"dsa5","category":"DSA","topic":"Sliding Window","question":"Sliding-window techniques are most naturally suited to problems involving what?","options":["Contiguous subarrays or substrings","Only binary trees","Only graphs","Compiler parsing"],"difficulty":"Easy","correct_index":0,"explanation":"A moving window maintains information about a contiguous range efficiently."},
    {"id":"dsa6","category":"DSA","topic":"Stacks","question":"Which data structure is the natural choice for matching parentheses?","options":["Queue","Stack","Heap","Graph"],"difficulty":"Easy","correct_index":1,"explanation":"Opening brackets are pushed and matched when closing brackets are encountered."},
    {"id":"dsa7","category":"DSA","topic":"Queues","question":"Which principle does a standard queue follow?","options":["LIFO","FIFO","Random access","Divide and conquer"],"difficulty":"Easy","correct_index":1,"explanation":"The first element inserted is the first element removed."},
    {"id":"dsa8","category":"DSA","topic":"Linked Lists","question":"What is the usual time to insert a node at the head of a singly linked list?","options":["O(1)","O(log n)","O(n)","O(n log n)"],"difficulty":"Easy","correct_index":0,"explanation":"Only the head pointer needs to be updated."},
    {"id":"dsa9","category":"DSA","topic":"Trees","question":"Which traversal of a binary search tree visits keys in sorted order?","options":["Preorder","Inorder","Postorder","Level order only"],"difficulty":"Easy","correct_index":1,"explanation":"Inorder traversal visits left subtree, node, then right subtree, producing sorted keys in a BST."},
    {"id":"dsa10","category":"DSA","topic":"Heaps","question":"What is the time complexity of extracting the minimum from a binary min-heap?","options":["O(1) always including reheapification","O(log n)","O(n)","O(n log n)"],"difficulty":"Medium","correct_index":1,"explanation":"Removing the root is followed by heapify-down, which takes O(log n)."},
    {"id":"dsa11","category":"DSA","topic":"Graphs","question":"Which algorithm finds shortest paths from a source when all edge weights are non-negative?","options":["Dijkstra's algorithm","Kruskal's algorithm","Binary search","Floyd's cycle detection"],"difficulty":"Medium","correct_index":0,"explanation":"Dijkstra repeatedly finalizes the closest unvisited vertex and works with non-negative weights."},
    {"id":"dsa12","category":"DSA","topic":"Graphs","question":"What does BFS naturally use to explore a graph level by level?","options":["Queue","Stack only","Heap only","Recursion only"],"difficulty":"Easy","correct_index":0,"explanation":"A queue preserves the level-order frontier used by breadth-first search."},
    {"id":"dsa13","category":"DSA","topic":"Dynamic Programming","question":"A dynamic-programming solution usually combines which two ideas?","options":["Overlapping subproblems and optimal substructure","Sorting and hashing","Recursion and randomization only","Pointers and queues"],"difficulty":"Medium","correct_index":0,"explanation":"DP stores results of overlapping subproblems and relies on an optimal-substructure relationship."},
    {"id":"dsa14","category":"DSA","topic":"Recursion","question":"What is essential for a recursive function to terminate?","options":["A base case","A global variable","A hash table","A loop with break"],"difficulty":"Easy","correct_index":0,"explanation":"The base case stops further recursive calls."},
    {"id":"dsa15","category":"DSA","topic":"Sorting","question":"Which sorting algorithm has O(n log n) worst-case time and is not in-place in its standard array implementation?","options":["Merge sort","Insertion sort","Bubble sort","Selection sort"],"difficulty":"Medium","correct_index":0,"explanation":"Merge sort guarantees O(n log n) time but typically uses O(n) auxiliary space for arrays."},
    {"id":"dsa16","category":"DSA","topic":"Matrices","question":"For a 2D peak-element problem, what is a useful optimization over checking every cell?","options":["Binary-search one dimension and inspect a maximum in the other","Sort the entire matrix first","Convert the matrix to strings","Use nested loops without stopping"],"difficulty":"Medium","correct_index":0,"explanation":"Choosing a maximum along a row or column lets you discard a region and achieve sublinear behavior in one dimension."},
    {"id":"dsa17","category":"DSA","topic":"Complexity","question":"If an algorithm performs 3n + 20 operations, what is its asymptotic complexity?","options":["O(1)","O(log n)","O(n)","O(n²)"],"difficulty":"Easy","correct_index":2,"explanation":"Constant factors and additive constants are ignored in Big-O notation."},
    {"id":"dsa18","category":"DSA","topic":"Graphs","question":"Which data structure is commonly used for an adjacency-list representation?","options":["Array/list per vertex","Only a stack","Only a string","A single integer"],"difficulty":"Easy","correct_index":0,"explanation":"Each vertex stores a collection of its adjacent vertices or edges."},

    # Aptitude
    {"id":"apt1","category":"Aptitude","topic":"Percentages","question":"A price increases from 200 to 250. What is the percentage increase?","options":["20%","25%","30%","50%"],"difficulty":"Easy","correct_index":1,"explanation":"The increase is 50; 50/200 × 100 = 25%."},
    {"id":"apt2","category":"Aptitude","topic":"Ratios","question":"If A:B = 2:3 and B:C = 4:5, what is A:C?","options":["2:5","8:15","3:5","4:15"],"difficulty":"Medium","correct_index":1,"explanation":"Make B equal: 2:3 becomes 8:12 and 4:5 becomes 12:15, so A:C = 8:15."},
    {"id":"apt3","category":"Aptitude","topic":"Averages","question":"The average of 10, 20 and 30 is:","options":["15","20","25","30"],"difficulty":"Easy","correct_index":1,"explanation":"(10+20+30)/3 = 20."},
    {"id":"apt4","category":"Aptitude","topic":"Time and Work","question":"If a person completes a job in 10 days at a constant rate, what fraction of the job is completed per day?","options":["1/5","1/10","1/20","10"],"difficulty":"Easy","correct_index":1,"explanation":"At a constant rate, one day completes 1/10 of the total work."},
    {"id":"apt5","category":"Aptitude","topic":"Speed Distance Time","question":"A car travels 120 km in 3 hours. Its average speed is:","options":["30 km/h","40 km/h","60 km/h","90 km/h"],"difficulty":"Easy","correct_index":1,"explanation":"Speed = distance/time = 120/3 = 40 km/h."},
    {"id":"apt6","category":"Aptitude","topic":"Probability","question":"What is the probability of getting heads on one fair coin toss?","options":["0","1/4","1/2","1"],"difficulty":"Easy","correct_index":2,"explanation":"There are two equally likely outcomes and one is heads."},
    {"id":"apt7","category":"Aptitude","topic":"Profit and Loss","question":"An item bought for ₹500 is sold for ₹600. The profit percentage is:","options":["10%","15%","20%","25%"],"difficulty":"Easy","correct_index":2,"explanation":"Profit = 100; 100/500 × 100 = 20%."},
    {"id":"apt8","category":"Aptitude","topic":"Number Series","question":"What is the next number: 2, 4, 8, 16, ?","options":["20","24","32","36"],"difficulty":"Easy","correct_index":2,"explanation":"Each term is multiplied by 2."},
    {"id":"apt9","category":"Aptitude","topic":"Permutations","question":"How many ways can 3 distinct people be arranged in a row?","options":["3","6","9","12"],"difficulty":"Easy","correct_index":1,"explanation":"There are 3! = 6 permutations."},
    {"id":"apt10","category":"Aptitude","topic":"Logical Reasoning","question":"If all developers are graduates and Ravi is a developer, what follows logically?","options":["Ravi is a graduate","All graduates are developers","Ravi is not a developer","No conclusion"],"difficulty":"Easy","correct_index":0,"explanation":"The premise directly implies Ravi belongs to the set of graduates."},
    {"id":"apt11","category":"Aptitude","topic":"Mixtures","question":"A solution contains 20 L water and 10 L juice. What fraction of the solution is juice?","options":["1/2","1/3","2/3","1/4"],"difficulty":"Easy","correct_index":1,"explanation":"Total volume is 30 L and juice is 10 L, so the fraction is 10/30 = 1/3."},
    {"id":"apt12","category":"Aptitude","topic":"Clocks","question":"How many degrees does the minute hand move in 10 minutes?","options":["30°","60°","90°","120°"],"difficulty":"Easy","correct_index":1,"explanation":"The minute hand moves 6° per minute, so 10 minutes gives 60°."},

    # Core CS
    {"id":"cs1","category":"Core CS","topic":"Operating Systems","question":"Which scheduling algorithm gives each process a fixed time slice in rotation?","options":["Round Robin","FCFS only","SJF only","Deadlock avoidance"],"difficulty":"Easy","correct_index":0,"explanation":"Round Robin cycles through ready processes using a time quantum."},
    {"id":"cs2","category":"Core CS","topic":"Operating Systems","question":"Which condition is required for a deadlock to occur?","options":["Mutual exclusion","Compilation","Caching","Sorting"],"difficulty":"Medium","correct_index":0,"explanation":"Mutual exclusion is one of the necessary Coffman conditions for deadlock."},
    {"id":"cs3","category":"Core CS","topic":"DBMS","question":"Which normal form primarily removes partial dependency on part of a composite key?","options":["1NF","2NF","3NF","BCNF only"],"difficulty":"Medium","correct_index":1,"explanation":"Second normal form removes partial functional dependencies on a composite candidate key."},
    {"id":"cs4","category":"Core CS","topic":"DBMS","question":"Which SQL clause filters rows before grouping?","options":["WHERE","HAVING","ORDER BY","LIMIT"],"difficulty":"Easy","correct_index":0,"explanation":"WHERE filters individual rows before GROUP BY; HAVING filters groups after aggregation."},
    {"id":"cs5","category":"Core CS","topic":"DBMS","question":"What does an SQL INNER JOIN return?","options":["Only matching rows between the joined tables","All left rows regardless of match","All right rows regardless of match","Every possible pair"],"difficulty":"Easy","correct_index":0,"explanation":"INNER JOIN returns rows where the join condition matches in both tables."},
    {"id":"cs6","category":"Core CS","topic":"Computer Networks","question":"Which protocol is connection-oriented and reliable at the transport layer?","options":["UDP","TCP","IP","ARP"],"difficulty":"Easy","correct_index":1,"explanation":"TCP establishes a connection and provides ordered, reliable byte-stream delivery."},
    {"id":"cs7","category":"Core CS","topic":"Computer Networks","question":"What does DNS primarily translate?","options":["Domain names to IP addresses","IP addresses to CPU instructions","SQL to HTML","Files to packets"],"difficulty":"Easy","correct_index":0,"explanation":"DNS resolves human-readable domain names into network addresses such as IPs."},
    {"id":"cs8","category":"Core CS","topic":"OOP","question":"Which OOP principle bundles data and methods that operate on that data?","options":["Encapsulation","Recursion","Compilation","Normalization"],"difficulty":"Easy","correct_index":0,"explanation":"Encapsulation combines state and behavior behind a defined interface."},
    {"id":"cs9","category":"Core CS","topic":"OOP","question":"Which concept allows a subclass to provide its own implementation of a parent method?","options":["Method overriding","Method overloading only","Normalization","Indexing"],"difficulty":"Easy","correct_index":0,"explanation":"Overriding replaces inherited behavior with a subclass-specific implementation."},
    {"id":"cs10","category":"Core CS","topic":"Databases","question":"What is a database index mainly used for?","options":["Speeding up selected queries","Encrypting every row","Replacing backups","Removing all duplicates automatically"],"difficulty":"Easy","correct_index":0,"explanation":"Indexes trade storage and write overhead for faster lookup on indexed columns."},
    {"id":"cs11","category":"Core CS","topic":"HTTP","question":"Which HTTP status code commonly means 'Not Found'?","options":["200","301","404","500"],"difficulty":"Easy","correct_index":2,"explanation":"404 indicates that the requested resource could not be found."},
    {"id":"cs12","category":"Core CS","topic":"Software Engineering","question":"What is the main purpose of version control such as Git?","options":["Track and manage changes to source code","Compile code automatically in every case","Replace databases","Host DNS records"],"difficulty":"Easy","correct_index":0,"explanation":"Version control records project history and supports collaboration and rollback."},

    # Communication
    {"id":"com1","category":"Communication","topic":"Project Explanation","question":"Which structure is strongest for a concise project answer in an interview?","options":["Situation/Task → Action → Result","Only list technologies","Read the README aloud","Give unrelated background"],"difficulty":"Easy","correct_index":0,"explanation":"A STAR-style structure keeps the answer contextual, action-oriented and outcome-focused."},
    {"id":"com2","category":"Communication","topic":"Behavioral Interviews","question":"When describing a team conflict, what should you emphasize most?","options":["Blaming the other person","The situation, your response and the outcome","Only the final result","Why conflict is impossible"],"difficulty":"Easy","correct_index":1,"explanation":"Interviewers want evidence of judgment, communication and ownership."},
    {"id":"com3","category":"Communication","topic":"Technical Explanation","question":"If an interviewer says they do not understand your explanation, what is the best response?","options":["Repeat the same sentence louder","Reframe it with a simpler example","End the interview answer","Use more jargon"],"difficulty":"Easy","correct_index":1,"explanation":"Adapting the explanation to the listener demonstrates communication skill."},
    {"id":"com4","category":"Communication","topic":"Project Impact","question":"Which project bullet is strongest?","options":["Worked on website","Used React","Built a dashboard used by 500 students and reduced manual reporting time by 60%","Made a project"],"difficulty":"Medium","correct_index":2,"explanation":"It combines action, technology/context, scale and measurable impact."},
    {"id":"com5","category":"Communication","topic":"Interview Answers","question":"What should you do when you do not know an interview question?","options":["Invent a fact confidently","Explain what you know and reason toward an answer","Stay silent","Change the topic"],"difficulty":"Easy","correct_index":1,"explanation":"Transparent reasoning demonstrates problem solving without pretending to know something you do not."},
    {"id":"com6","category":"Communication","topic":"Resume Language","question":"Which phrase is more evidence-oriented?","options":["Responsible for coding","Helped with many things","Implemented caching that reduced API latency by 35%","Worked hard"],"difficulty":"Medium","correct_index":2,"explanation":"It states an action and measurable result instead of vague responsibility language."},
    {"id":"com7","category":"Communication","topic":"Presentation","question":"A good technical answer should generally begin with:","options":["The core idea or conclusion","Every implementation detail","An unrelated story","An apology"],"difficulty":"Easy","correct_index":0,"explanation":"Leading with the core idea gives the interviewer a clear frame before details."},
    {"id":"com8","category":"Communication","topic":"Behavioral Interviews","question":"Which response best demonstrates ownership after a mistake?","options":["It was entirely someone else's fault","I identified the issue, fixed it and changed the process to prevent recurrence","I never make mistakes","I ignored it"],"difficulty":"Easy","correct_index":1,"explanation":"Ownership includes acknowledging the issue, taking corrective action and learning from it."},
]



def public_user(u):
    return {"id":u["id"],"name":u["name"],"email":u["email"],"role":u["role"],"profile_complete":bool(u["profile_complete"])}


def current_user(session: Optional[str]):
    if not session:
        return None
    with db() as c:
        row = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?", (session, datetime.now(timezone.utc).isoformat())).fetchone()
    return row


def require_user(session):
    u = current_user(session)
    if not u:
        raise HTTPException(401, "Not authenticated")
    return u


class LoginBody(BaseModel):
    email: str
    password: str


class SignupBody(BaseModel):
    name: str
    email: str
    password: str
    role: str = "student"


class AnswerBody(BaseModel):
    question_id: str
    selected_index: Optional[int] = None


class TaskBody(BaseModel):
    status: str


class ResumeAnalyzeBody(BaseModel):
    target_role: str = "Software Engineer"
    job_description: str = ""


def make_session(user_id: str, response: Response):
    token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(days=14)
    with db() as c:
        c.execute("INSERT INTO sessions VALUES (?,?,?)", (token, user_id, expiry.isoformat()))
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="none" if COOKIE_SECURE else "lax",
        secure=COOKIE_SECURE,
        max_age=14 * 24 * 3600,
        path="/",
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "preceptron-api", "version": "2.0.0"}


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response):
    email = body.email.strip().lower()
    logger.info("[AUTH] Login attempt for: %s", email)
    try:
        with db() as c:
            u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    except Exception as exc:
        logger.error("[AUTH] DB error fetching user for %s: %s", email, exc)
        raise HTTPException(500, "Database error during login")
    if not u:
        logger.warning("[AUTH] User not found: %s", email)
        raise HTTPException(401, "Invalid email or password")
    stored_pw = u["password"] or ""
    if not verify_password(body.password, stored_pw):
        logger.warning("[AUTH] Password verification failed for: %s (hash prefix: %s)", email, stored_pw[:14] if stored_pw else "empty")
        raise HTTPException(401, "Invalid email or password")
    # Upgrade legacy plaintext password if encountered
    if stored_pw == body.password:
        logger.info("[AUTH] Upgrading plaintext password for: %s", email)
        with db() as c:
            c.execute("UPDATE users SET password=? WHERE id=?", (hash_password(body.password), u["id"]))
    try:
        make_session(u["id"], response)
    except Exception as exc:
        logger.error("[AUTH] Session creation failed for %s: %s", email, exc)
        raise HTTPException(500, "Session creation failed")
    logger.info("[AUTH] Login successful for: %s (role=%s)", email, u["role"])
    return {"user": public_user(u)}



@app.post("/api/auth/signup")
def signup(body: SignupBody, response: Response):
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    role = body.role if body.role in {"student", "tpo"} else "student"
    hashed_password = hash_password(body.password)
    with db() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone():
            raise HTTPException(409, "An account with this email already exists")
        uid = str(uuid.uuid4())
        c.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)", (uid, body.name, body.email.strip().lower(), hashed_password, role, 1, "", "CSE", 2027, "Software Engineer"))
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    make_session(uid, response)
    return {"user": public_user(u)}


@app.post("/api/auth/logout")
def logout(response: Response, session: Optional[str] = Cookie(None)):
    if session:
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token=?", (session,))
    response.delete_cookie(
        "session",
        samesite="none" if COOKIE_SECURE else "lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"message": "logged out"}


@app.get("/api/auth/me")
def me(session: Optional[str] = Cookie(None)):
    return public_user(require_user(session))


@app.get("/api/profile")
def profile(session: Optional[str] = Cookie(None)):
    u = require_user(session)
    return {"user_id":u["id"],"name":u["name"],"email":u["email"],"college":u["college"],"branch":u["branch"],"graduation_year":u["graduation_year"],"target_role":u["target_role"],"current_skill_level":"Intermediate","self_assessment":{"DSA":3,"SQL":2,"Communication":4}}


@app.get("/api/dashboard")
def dashboard(session: Optional[str] = Cookie(None)):
    u = require_user(session)
    if u["role"] != "student": raise HTTPException(403, "Student access required")
    with db() as c:
        tasks = [dict(x) for x in c.execute("SELECT * FROM tasks WHERE date='Today' ORDER BY id LIMIT 3").fetchall()]
    return {"user":public_user(u),"readiness_score":71,"skill_scores":SKILLS,"roadmap_progress":61,"today_tasks":tasks,"recent_assessment":{"id":"a1","score":74,"created_at":"2026-09-10"},"practice_stats":{"attempted":42,"correct":31,"accuracy":74},"upcoming_interview":{"id":"i1","created_at":"2026-09-13","completed":False},"weakest_skills":["SQL","Problem Solving"],"has_assessment":True}


def _history_for_user(user_id: str, table: str):
    with db() as c:
        rows = c.execute(f"SELECT question_id, correct, category, topic, difficulty FROM {table} WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def _adaptive_questions(user_id: str, limit: int = 12):
    history = _history_for_user(user_id, "assessment_attempts")
    attempted = {h["question_id"] for h in history}
    topic_stats = {}
    category_stats = {}
    for h in history:
        t = topic_stats.setdefault(h["topic"], [0, 0]); t[0] += 1; t[1] += int(h["correct"])
        c = category_stats.setdefault(h["category"], [0, 0]); c[0] += 1; c[1] += int(h["correct"])

    def score(q):
        ts = topic_stats.get(q["topic"])
        cs = category_stats.get(q["category"])
        weakness = 0.0
        if ts: weakness += max(0, 1 - ts[1] / ts[0]) * 8
        if cs: weakness += max(0, 1 - cs[1] / cs[0]) * 4
        difficulty_bonus = {"Easy": 1, "Medium": 2, "Hard": 3}.get(q["difficulty"], 1)
        fresh_bonus = 5 if q["id"] not in attempted else -20
        return weakness + difficulty_bonus + fresh_bonus

    pool = sorted(QUESTIONS, key=lambda q: (-score(q), q["id"]))
    fresh = [q for q in pool if q["id"] not in attempted]
    # Keep category balance while still prioritizing weak areas.
    selected = []
    per_category = {"DSA": 0, "Aptitude": 0, "Core CS": 0, "Communication": 0}
    for q in fresh + pool:
        if len(selected) >= limit: break
        cap = 4 if len(history) < 12 else 6
        if per_category.get(q["category"], 0) >= cap: continue
        selected.append(q); per_category[q["category"]] += 1
    return selected


@app.get("/api/assessment/questions")
def assessment_questions(session: Optional[str] = Cookie(None)):
    u = require_user(session)
    return _adaptive_questions(u["id"], 12)


@app.post("/api/assessment/answer")
def assessment_answer(body: AnswerBody, session: Optional[str] = Cookie(None)):
    u = require_user(session)
    q = next((x for x in QUESTIONS if x["id"] == body.question_id), None)
    if not q: raise HTTPException(404, "Question not found")
    correct = body.selected_index == q["correct_index"]
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute("INSERT INTO assessment_attempts VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), u["id"], q["id"], body.selected_index, int(correct), q["category"], q["topic"], q["difficulty"], now))
        row = c.execute("SELECT COUNT(*) n, COALESCE(SUM(correct),0) c FROM assessment_attempts WHERE user_id=?", (u["id"],)).fetchone()
    accuracy = round(row["c"] / row["n"] * 100) if row["n"] else 0
    return {"correct":correct,"correct_index":q["correct_index"],"explanation":q["explanation"],"attempted":row["n"],"accuracy":accuracy}


@app.get("/api/roadmap")
def roadmap(session: Optional[str] = Cookie(None)):
    require_user(session)
    with db() as c:
        tasks = [dict(x) for x in c.execute("SELECT * FROM tasks ORDER BY (CASE WHEN date='Today' THEN 1 ELSE 0 END) DESC, id").fetchall()]
    done = sum(t["status"] == "done" for t in tasks)
    return {"tasks":tasks,"progress":round(done/len(tasks)*100),"weekly_goal":"Complete 5 focused tasks"}


@app.patch("/api/roadmap/{task_id}")
def update_task(task_id: str, body: TaskBody, session: Optional[str] = Cookie(None)):
    require_user(session)
    if body.status not in {"todo", "done"}: raise HTTPException(400, "Invalid task status")
    with db() as c:
        c.execute("UPDATE tasks SET status=? WHERE id=?", (body.status, task_id))
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row: raise HTTPException(404, "Task not found")
    return dict(row)


@app.get("/api/practice/stats")
def practice_stats(session: Optional[str] = Cookie(None)):
    u = require_user(session)
    with db() as c:
        row = c.execute("SELECT COUNT(*) n, COALESCE(SUM(correct),0) c FROM practice_attempts WHERE user_id=?", (u["id"],)).fetchone()
    n, correct = row["n"], row["c"]
    return {"attempted":n,"correct":correct,"accuracy":round(correct/n*100) if n else 0}


@app.get("/api/practice/next")
def practice_next(session: Optional[str] = Cookie(None)):
    u = require_user(session)
    history = _history_for_user(u["id"], "practice_attempts")
    attempted = {h["question_id"] for h in history}
    # Blend assessment weakness with practice freshness.
    candidates = _adaptive_questions(u["id"], len(QUESTIONS))
    candidates = [q for q in candidates if q["id"] not in attempted] or candidates
    return candidates[0]


@app.post("/api/practice/submit")
def practice_submit(body: AnswerBody, session: Optional[str] = Cookie(None)):
    u = require_user(session)
    q = next((x for x in QUESTIONS if x["id"] == body.question_id), None)
    if not q: raise HTTPException(404, "Question not found")
    correct = body.selected_index == q["correct_index"]
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute("INSERT INTO practice_attempts VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), u["id"], q["id"], body.selected_index, int(correct), q["category"], q["topic"], q["difficulty"], now))
        row = c.execute("SELECT COUNT(*) n, COALESCE(SUM(correct),0) c FROM practice_attempts WHERE user_id=?", (u["id"],)).fetchone()
    accuracy = round(row["c"] / row["n"] * 100) if row["n"] else 0
    return {"correct":correct,"explanation":q["explanation"],"correct_index":q["correct_index"],"attempted":row["n"],"accuracy":accuracy}


@app.get("/api/interview/next")
def interview_next(session: Optional[str] = Cookie(None)):
    require_user(session)
    return {"id":"i1","question_index":1,"total_questions":5,"question":"Explain a project you built, the problem it solved, and one technical trade-off you made.","completed":False}


@app.post("/api/interview/submit")
def interview_submit(answer: dict, session: Optional[str] = Cookie(None)):
    require_user(session)
    text = (answer.get("answer") or "").strip()
    score = min(95, max(45, 58 + len(text)//35))
    return {"id":"i1","question_index":2,"total_questions":5,"question":"How would you optimize a slow API endpoint?","completed":False,"feedback":{"overall_score":score,"technical_clarity":min(95, score+3),"communication":min(95, score+6),"relevance":score,"strengths":["Clear ownership language","Good opportunity to quantify impact"],"improvements":["Name the architecture or algorithm explicitly","Add one measurable result"],"suggested_answer":"Use a concise STAR structure: context, your technical decision, implementation, measurable impact."}}


@app.get("/api/analytics")
def analytics(session: Optional[str] = Cookie(None)):
    require_user(session)
    return {"readiness_score":71,"skill_scores":SKILLS,"assessment_history":[{"score":62,"created_at":"2026-08-12"},{"score":68,"created_at":"2026-08-27"},{"score":74,"created_at":"2026-09-10"}],"practice_stats":{"attempted":42,"correct":31,"accuracy":74},"roadmap_progress":61,"interview_scores":[68,76],"formula":"Weighted blend of assessment, skill scores, practice accuracy and roadmap progress.","disclaimer":"Readiness is a guidance signal, not a hiring prediction."}


@app.get("/api/resume/projects")
def projects(session: Optional[str] = Cookie(None)):
    require_user(session)
    return [{"id":"p1","project_name":"Preceptron","problem_solved":"Students struggle to translate placement feedback into a concrete plan.","technologies":"React, TypeScript, FastAPI","contribution":"Designed the product flow and readiness dashboard.","impact":"Turns fragmented preparation into measurable next actions.","suggestions":["Add outcome tracking","Connect college data"],"created_at":"2026-09-01"}]


# ---- Resume intelligence -------------------------------------------------

def extract_text(filename: str, content: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == ".docx":
        from docx import Document
        from io import BytesIO
        doc = Document(BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    if ext in {".txt", ".md"}:
        return content.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Upload PDF, DOCX, TXT or MD.")


def section(text: str, heading: str) -> str:
    m = re.search(rf"(?im)^\s*{re.escape(heading)}\s*$", text)
    return m.group(0) if m else ""


def local_resume_analysis(text: str, role: str, jd: str) -> dict:
    clean = re.sub(r"\s+", " ", text).strip()
    lower = clean.lower()
    words = clean.split()
    bullets = len(re.findall(r"(?:^|\n)\s*[•●▪◦*-]\s+", text))
    numbers = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", clean))
    verbs = sum(1 for v in ["built","developed","designed","implemented","optimized","led","created","automated","improved","reduced","increased","deployed"] if re.search(rf"\b{v}\b", lower))
    sections = {name: bool(re.search(rf"(?i)\b{name}\b", clean)) for name in ["experience","education","projects","skills","certifications"]}
    contact = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", clean))
    phone = bool(re.search(r"(?:\+?\d[\d\s().-]{8,}\d)", clean))
    target_terms = re.findall(r"[a-zA-Z][a-zA-Z+#.-]{2,}", jd.lower()) if jd else []
    jd_terms = sorted(set(t for t in target_terms if t not in {"the","and","with","for","from","that","this","are","you","your"}))
    matched = [t for t in jd_terms[:80] if re.search(rf"\b{re.escape(t)}\b", lower)]
    missing = [t for t in jd_terms[:30] if t not in matched]

    score = 45
    score += min(12, len(words)//55)
    score += 8 if sections["experience"] else 0
    score += 8 if sections["projects"] else 0
    score += 6 if sections["skills"] else 0
    score += 5 if sections["education"] else 0
    score += min(8, numbers * 2)
    score += min(5, verbs)
    score += 3 if contact and phone else 0
    score -= 7 if len(words) < 180 else 0
    score -= 5 if len(words) > 950 else 0
    score = max(35, min(95, score))

    suggestions = []
    if numbers < 4: suggestions.append("Add quantified impact to 3–5 bullets: %, time saved, scale, latency, users, revenue, accuracy, or throughput.")
    if verbs < 5: suggestions.append("Replace passive descriptions with strong action verbs such as built, optimized, automated, led, reduced, or increased.")
    if not sections["skills"]: suggestions.append("Add a compact technical-skills section aligned to the target role.")
    if not sections["projects"]: suggestions.append("Add 2–3 relevant projects with the problem, technical decision, and measurable outcome.")
    if len(words) > 950: suggestions.append("Tighten the resume; remove low-signal detail and keep the strongest evidence near the top.")
    if len(words) < 180: suggestions.append("Add evidence: projects, internships, coursework, certifications, or outcomes so the resume does not read as under-developed.")
    suggestions.append("For each major bullet, use: Action + technical method + scope + measurable result.")
    suggestions.append(f"Tailor the headline and top third specifically for {role} rather than using a generic objective.")

    rewrites = []
    sample = re.search(r"(?im)^\s*[-•]\s*(.+)$", text)
    if sample:
        original = sample.group(1).strip()
        rewrites.append({"before": original, "after": f"Strengthen this bullet with the technology used and a quantified outcome: {original.rstrip('.')}"})
    rewrites.append({"before":"Worked on a project","after":"Built [project] using [stack] to solve [problem], improving [metric] by [X]% for [scope]."})
    rewrites.append({"before":"Responsible for development","after":"Implemented [feature] with [technology], reducing [time/errors/cost] by [X]% and supporting [scale]."})

    return {
        "score": score,
        "engine": "local-resume-intelligence",
        "summary": f"Your resume has a solid base for {role}, but the strongest opportunity is to make impact and role alignment more explicit.",
        "strengths": [
            "Contact information is present." if contact else "Content can be made more recruiter-friendly by adding clear contact information.",
            f"Detected {numbers} numeric/quantified signals across the document.",
            f"Detected {verbs} impact-oriented action verbs.",
        ],
        "gaps": [
            name.title() for name, ok in sections.items() if not ok
        ] or ["More measurable outcomes", "Stronger role-specific keyword alignment"],
        "suggestions": suggestions,
        "ats_keywords_matched": matched[:12],
        "ats_keywords_missing": missing[:12],
        "rewrites": rewrites,
        "word_count": len(words),
        "sections": sections,
    }


def maybe_llm_analysis(base: dict, text: str, role: str, jd: str) -> dict:
    key = os.getenv("OPENAI_API_KEY")
    if not key or os.getenv("AI_PROVIDER", "local").lower() != "openai":
        return base
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    prompt = f"""You are Preceptron Resume Intelligence. Analyze the resume for a {role} role. Return ONLY valid JSON with keys: summary, strengths (array), gaps (array), suggestions (array), ats_keywords_matched (array), ats_keywords_missing (array), rewrites (array of {{before,after}}), score (integer 0-100). Be concrete, truthful, ATS-aware, and never invent experience. Job description: {jd[:7000]} Resume: {text[:18000]}"""
    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "input": prompt}, timeout=45,
        )
        r.raise_for_status()
        data = r.json()
        output = data.get("output", [])
        raw = ""
        for item in output:
            for part in item.get("content", []):
                if part.get("type") in {"output_text", "text"}:
                    raw += part.get("text", "")
        parsed = json.loads(raw[raw.find("{"):raw.rfind("}")+1])
        parsed["engine"] = "openai"
        parsed["word_count"] = base["word_count"]
        parsed["sections"] = base["sections"]
        return parsed
    except Exception:
        return base


@app.post("/api/resume/analyze")
async def resume_analyze(
    target_role: str = Form("Software Engineer"),
    job_description: str = Form(""),
    resume: UploadFile = File(...),
    session: Optional[str] = Cookie(None),
):
    u = require_user(session)
    if u["role"] != "student": raise HTTPException(403, "Student access required")
    if not resume.filename: raise HTTPException(400, "Choose a resume file")
    content = await resume.read()
    if len(content) > 6 * 1024 * 1024: raise HTTPException(413, "Resume must be under 6 MB")
    try:
        text = extract_text(resume.filename, content)
    except Exception as e:
        raise HTTPException(400, str(e))
    if len(text.strip()) < 80:
        raise HTTPException(400, "We could not extract enough text. Try a text-based PDF or DOCX.")
    result = maybe_llm_analysis(local_resume_analysis(text, target_role, job_description), text, target_role, job_description)
    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute("INSERT INTO resume_analyses VALUES (?,?,?,?,?,?,?)", (analysis_id, u["id"], resume.filename, target_role, result["score"], json.dumps(result), now))
    return {"id":analysis_id,"filename":resume.filename,"target_role":target_role,"created_at":now,"result":result}


@app.get("/api/resume/analyses")
def resume_analyses(session: Optional[str] = Cookie(None)):
    u = require_user(session)
    with db() as c:
        rows = c.execute("SELECT id,filename,role,score,created_at FROM resume_analyses WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (u["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/tpo/summary")
def tpo_summary(session: Optional[str] = Cookie(None)):
    u = require_user(session)
    if u["role"] != "tpo": raise HTTPException(403, "TPO access required")
    return {"total_students":482,"average_readiness":67,"average_assessment":72,"roadmap_completion":61,"top_skill_gaps":[{"category":"DSA","students":184},{"category":"SQL","students":151},{"category":"Problem Solving","students":137},{"category":"Core CS","students":96}],"students_needing_support":119,"filters":{"branches":["CSE","ECE","IT","ME"],"graduation_years":[2026,2027],"target_roles":["Software Engineer","Data Analyst","Product Engineer"]}}


# Serve the built frontend if present (e.g. single-container mode), or return API info.
@app.get("/{full_path:path}")
def frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not Found")
    if FRONTEND_DIST.exists():
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
    if full_path == "":
        return {"status": "ok", "service": "preceptron-api", "version": "2.0.0", "docs": "/docs"}
    raise HTTPException(404, "Not Found")
