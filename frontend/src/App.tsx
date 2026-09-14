import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Code2,
  FileText,
  GitFork,
  LayoutDashboard,
  LogOut,
  Menu,
  Sparkles,
  Target,
  TrendingUp,
  User,
  Users,
  Video,
  X,
  ShieldCheck,
  Settings,
  UploadCloud,
  FileSearch,
  AlertTriangle,
  Check,
  Brain,
  Zap,
  CircleHelp,
} from "lucide-react";
import { apiGet, apiPost, apiPatch, apiUpload } from "./lib/api";
import type {
  UserPublic,
  RoadmapTask,
  SkillScore,
  TpoSummary,
  ResumeAnalysis,
} from "./lib/types";
import "./index.css";

const studentNav = [
  ["Dashboard", "/dashboard", LayoutDashboard],
  ["Assessment", "/assessment", ClipboardCheck],
  ["Roadmap", "/roadmap", GitFork],
  ["Practice", "/practice", Code2],
  ["Mock Interview", "/mock-interview", Video],
  ["Resume AI", "/resume", FileText],
  ["Analytics", "/analytics", BarChart3],
  ["Profile", "/profile", User],
] as const;
const tpoNav = [
  ["Cohort Dashboard", "/tpo", ShieldCheck],
  ["Skill Gaps", "/tpo/skill-gaps", BarChart3],
  ["Students", "/tpo/students", Users],
  ["Settings", "/tpo/settings", Settings],
] as const;

function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`card ${className}`}>{children}</div>;
}
function Pill({
  children,
  tone = "indigo",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`pill ${tone}`}>{children}</span>;
}
function Progress({ value }: { value: number }) {
  return (
    <div className="progress">
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
function Loading() {
  return (
    <div className="loading">
      <div className="spinner" />
    </div>
  );
}
function PageHead({
  eyebrow,
  title,
  desc,
  action,
}: {
  eyebrow: string;
  title: ReactNode;
  desc: string;
  action?: ReactNode;
}) {
  return (
    <div className="pageHead">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
      {action}
    </div>
  );
}

function Login({ onLogin }: { onLogin: (u: UserPublic) => void }) {
  const [email, setEmail] = useState("student@demo.com"),
    [password, setPassword] = useState("demo123"),
    [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const r = await apiPost<{ user: UserPublic }>("/auth/login", {
        email,
        password,
      });
      onLogin(r.user);
    } catch {
      setError(
        "Login failed. Use the demo buttons or your account credentials.",
      );
    }
  };
  return (
    <div className="login">
      <div className="loginPanel">
        <div className="brand center">
          <div className="brandMark">P</div>
          <div>
            <b>Preceptron</b>
            <small>Placement intelligence</small>
          </div>
        </div>
        <div className="eyebrow">FROM FEEDBACK TO ACTION</div>
        <h1>
          Know what to improve.
          <br />
          <span>Know what to do next.</span>
        </h1>
        <p className="muted">
          Preceptron turns readiness signals into a personalized action loop —
          assessment, diagnosis, roadmap, practice, interview and resume
          improvement.
        </p>
        <form onSubmit={submit}>
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <div className="error">{error}</div>}
          <button className="primary wide">
            Enter workspace <ArrowRight size={17} />
          </button>
        </form>
        <div className="demoRow">
          <button
            onClick={() => {
              setEmail("student@demo.com");
              setPassword("demo123");
            }}
          >
            Student demo
          </button>
          <button
            onClick={() => {
              setEmail("tpo@demo.com");
              setPassword("demo123");
            }}
          >
            TPO demo
          </button>
        </div>
      </div>
      <div className="loginVisual">
        <div className="pitchQuote">
          “Preparation shouldn't end at a score.
          <br />
          <b>It should produce the next action.</b>”
        </div>
        <div className="visualCards">
          <div>
            <Target />
            <b>71%</b>
            <small>readiness</small>
          </div>
          <div>
            <TrendingUp />
            <b>+12</b>
            <small>points this month</small>
          </div>
          <div>
            <Brain />
            <b>AI</b>
            <small>resume intelligence</small>
          </div>
        </div>
      </div>
    </div>
  );
}

function Shell({
  user,
  onLogout,
  children,
}: {
  user: UserPublic;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const nav = user.role === "tpo" ? tpoNav : studentNav;
  return (
    <div className="app">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brandMark">P</div>
          <div>
            <b>Preceptron</b>
            <small>Placement intelligence</small>
          </div>
          <button className="iconBtn mobile" onClick={() => setOpen(false)}>
            <X size={18} />
          </button>
        </div>
        <div className="navLabel">
          {user.role === "tpo" ? "ADMIN WORKSPACE" : "YOUR PREPARATION"}
        </div>
        <nav>
          {nav.map(([label, path, Icon]) => (
            <Link
              onClick={() => setOpen(false)}
              className={loc.pathname === path ? "active" : ""}
              to={path}
              key={path}
            >
              <Icon size={18} />
              <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebarTip">
          <Sparkles size={17} />
          <div>
            <small>
              {user.role === "tpo" ? "Cohort insight" : "Your focus"}
            </small>
            <strong>
              {user.role === "tpo"
                ? "Help every student move forward"
                : "Know what to improve next"}
            </strong>
          </div>
        </div>
        <button className="logout" onClick={onLogout}>
          <LogOut size={17} /> Log out
        </button>
      </aside>
      {open && <div className="overlay" onClick={() => setOpen(false)} />}
      <main className="main">
        <header>
          <div className="headLeft">
            <button className="iconBtn mobile" onClick={() => setOpen(true)}>
              <Menu size={20} />
            </button>
            <div>
              <small>
                {user.role === "tpo" ? "COHORT VIEW" : "PLACEMENT READINESS"}
              </small>
              <b>
                {user.role === "tpo"
                  ? "TPO dashboard"
                  : "Your preparation workspace"}
              </b>
            </div>
          </div>
          <div className="user">
            <div>
              <b>{user.name}</b>
              <small>{user.role}</small>
            </div>
            <div className="avatar">{user.name[0]}</div>
          </div>
        </header>
        <div className="content">{children}</div>
      </main>
    </div>
  );
}

function Dashboard() {
  const [d, setD] = useState<any>();
  useEffect(() => {
    apiGet("/dashboard").then(setD);
  }, []);
  if (!d) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="STUDENT / DASHBOARD"
        title={<>Good to see you, {d.user.name.split(" ")[0]}. 👋</>}
        desc="Your readiness is a signal. Your plan turns that signal into progress."
        action={
          <Link className="primary" to="/assessment">
            Take assessment <ArrowRight size={17} />
          </Link>
        }
      />
      <div className="heroGrid">
        <Card className="readiness">
          <div className="miniHead">
            <span>READINESS SCORE</span>
            <Pill>On track</Pill>
          </div>
          <div className="scoreRow">
            <div className="ring">
              <b>{d.readiness_score}</b>
              <small>/100</small>
            </div>
            <div>
              <h2>Placement ready, with room to grow.</h2>
              <p>
                Your strongest skill is Communication. Your biggest opportunity
                is SQL and problem solving.
              </p>
            </div>
          </div>
          <Progress value={d.readiness_score} />
          <div className="scoreFoot">
            <span>
              <TrendingUp size={15} /> +7 since last assessment
            </span>
            <span>Target: 80+</span>
          </div>
        </Card>
        <Card className="focus">
          <div className="miniHead">
            <span>NEXT BEST ACTION</span>
            <Sparkles size={18} />
          </div>
          <h3>Close your SQL gap</h3>
          <p>
            Your SQL score is 55%. Two focused practice sessions can move this
            into your target range.
          </p>
          <Link to="/practice" className="textLink">
            Start SQL sprint <ArrowRight size={16} />
          </Link>
        </Card>
      </div>
      <div className="sectionTitle">
        <h2>Today's plan</h2>
        <Link to="/roadmap">
          View roadmap <ChevronRight size={15} />
        </Link>
      </div>
      <div className="taskGrid">
        {d.today_tasks.map((t: RoadmapTask) => (
          <Card key={t.id}>
            <div className="taskTop">
              <Pill tone={t.category === "SQL" ? "amber" : "indigo"}>
                {t.category}
              </Pill>
              <span>{t.estimated_minutes} min</span>
            </div>
            <h3>{t.title}</h3>
            <p>{t.details}</p>
            <div className="taskBottom">
              {t.status === "done" ? (
                <span className="done">
                  <CheckCircle2 size={16} /> Completed
                </span>
              ) : (
                <span className="muted">Ready to start</span>
              )}
              <Link to="/roadmap">
                <ArrowRight size={16} />
              </Link>
            </div>
          </Card>
        ))}
      </div>
      <div className="sectionTitle">
        <h2>Your skill profile</h2>
        <Link to="/analytics">
          Full analytics <ChevronRight size={15} />
        </Link>
      </div>
      <div className="skillGrid">
        {d.skill_scores.map((s: SkillScore) => (
          <Card key={s.category}>
            <div className="skillHead">
              <b>{s.category}</b>
              <strong>{s.score}</strong>
            </div>
            <Progress value={s.score} />
            <small>{s.label}</small>
          </Card>
        ))}
      </div>
      <Card className="loopBanner">
        <div>
          <Pill tone="green">THE PRECEPTRON LOOP</Pill>
          <h2>Measure → Diagnose → Act → Re-measure</h2>
          <p>
            Every module exists to move the learner from a score to a measurable
            next action.
          </p>
        </div>
        <div className="loopSteps">
          <span>1. Measure</span>
          <span>2. Diagnose</span>
          <span>3. Act</span>
          <span>4. Re-measure</span>
        </div>
      </Card>
    </>
  );
}

function Assessment() {
  const [qs, setQs] = useState<any[]>([]),
    [i, setI] = useState(0),
    [selected, setSelected] = useState<number | null>(null),
    [review, setReview] = useState<any>(null);
  useEffect(() => {
    apiGet<any[]>("/assessment/questions").then(setQs);
  }, []);
  if (!qs.length) return <Loading />;
  const q = qs[i];
  const submit = async () =>
    setReview(
      await apiPost("/assessment/answer", {
        question_id: q.id,
        selected_index: selected,
      }),
    );
  return (
    <>
      <PageHead
        eyebrow="STUDENT / ASSESSMENT"
        title="Measure your readiness."
        desc="A short checkpoint across the skills that matter for your target role."
      />
      <Card className="assessment">
        <div className="assessBar">
          <span>
            Question {i + 1} of {qs.length}
          </span>
          <span>
            <b>ADAPTIVE SET</b> · {q.category} · {q.difficulty}
          </span>
        </div>
        <Progress value={(i / qs.length) * 100} />
        <div className="question">
          <Pill>{q.topic}</Pill>
          <h2>{q.question}</h2>
          <div className="options">
            {q.options.map((o: string, idx: number) => (
              <button
                className={
                  (selected === idx ? "selected " : "") +
                  (review && idx === review.correct_index ? "correct" : "")
                }
                onClick={() => !review && setSelected(idx)}
                key={o}
              >
                <span>{String.fromCharCode(65 + idx)}</span>
                {o}
              </button>
            ))}
          </div>
          {review ? (
            <div className={review.correct ? "success" : "error"}>
              {review.correct ? "Correct! " : "Not quite. "}
              {review.explanation}
            </div>
          ) : (
            <button
              className="primary"
              disabled={selected === null}
              onClick={submit}
            >
              Check answer <ArrowRight size={16} />
            </button>
          )}
        </div>
        {review && (
          <button
            className="secondary"
            onClick={() => {
              if (i + 1 < qs.length) {
                setI(i + 1);
                setSelected(null);
                setReview(null);
              } else {
                window.location.reload();
              }
            }}
          >
            {i + 1 < qs.length
              ? "Next question"
              : "Start new adaptive assessment"}{" "}
            <ArrowRight size={16} />
          </button>
        )}
      </Card>
    </>
  );
}

function Roadmap() {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  const load = () => {
    setError("");
    apiGet("/roadmap")
      .then(setData)
      .catch((e: any) =>
        setError(
          e?.body?.detail ||
            "We couldn't load your roadmap. Check that the Preceptron API is running.",
        ),
      );
  };
  useEffect(load, []);
  if (error)
    return (
      <>
        <PageHead
          eyebrow="STUDENT / ROADMAP"
          title="Your next 7 days."
          desc="A focused sequence generated from your current skill gaps."
        />
        <Card>
          <div className="error">
            <AlertTriangle size={17} />
            {error}
          </div>
          <div className="actionRow">
            <button className="secondary" onClick={load}>
              Try again
            </button>
          </div>
        </Card>
      </>
    );
  if (!data) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="STUDENT / ROADMAP"
        title="Your next 7 days."
        desc="A focused sequence generated from your current skill gaps."
        action={<Pill tone="green">{data.progress}% complete</Pill>}
      />
      <Card>
        <div className="roadmapSummary">
          <div>
            <small>WEEKLY GOAL</small>
            <h3>{data.weekly_goal}</h3>
          </div>
          <div className="roadmapStat">
            <b>
              {
                data.tasks.filter((x: RoadmapTask) => x.status === "done")
                  .length
              }
            </b>{" "}
            / {data.tasks.length}
            <small>tasks done</small>
          </div>
        </div>
        <Progress value={data.progress} />
      </Card>
      <div className="roadmapList">
        {data.tasks.map((t: RoadmapTask) => (
          <Card key={t.id}>
            <button
              aria-label={`Mark ${t.title} ${t.status === "done" ? "incomplete" : "complete"}`}
              className={`check ${t.status === "done" ? "checked" : ""}`}
              onClick={async () => {
                try {
                  await apiPatch(`/roadmap/${t.id}`, {
                    status: t.status === "done" ? "todo" : "done",
                  });
                  load();
                } catch (e: any) {
                  setError(e?.body?.detail || "Could not update this task.");
                }
              }}
            >
              {t.status === "done" && <CheckCircle2 size={18} />}
            </button>
            <div className="roadmapBody">
              <div className="taskTop">
                <Pill tone={t.category === "SQL" ? "amber" : "indigo"}>
                  {t.category}
                </Pill>
                <span>
                  {t.date} · {t.estimated_minutes} min
                </span>
              </div>
              <h3>{t.title}</h3>
              <p>{t.details}</p>
            </div>
            <span className="difficulty">{t.difficulty}</span>
          </Card>
        ))}
      </div>
    </>
  );
}

function Practice() {
  const [q, setQ] = useState<any>();
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<any>();
  const load = () => {
    setResult(undefined);
    setSelected(null);
    apiGet("/practice/next").then(setQ);
  };
  useEffect(load, []);
  if (!q) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="STUDENT / PRACTICE"
        title="Practice the weak spot."
        desc="Targeted practice is more valuable than random volume when you know where the gap is."
      />
      <div className="practiceGrid">
        <Card className="practiceHero">
          <Pill tone="amber">SQL + DSA FOCUS</Pill>
          <h2>{q.question}</h2>
          <div className="options">
            {q.options.map((o: string, idx: number) => (
              <button
                className={selected === idx ? "selected" : ""}
                disabled={!!result}
                onClick={() => setSelected(idx)}
                key={o}
              >
                <span>{String.fromCharCode(65 + idx)}</span>
                {o}
              </button>
            ))}
          </div>
          {result ? (
            <div className={result.correct ? "success" : "error"}>
              {result.correct ? "Correct!" : "Not quite."} {result.explanation}
            </div>
          ) : (
            <button
              className="primary"
              disabled={selected === null}
              onClick={async () =>
                setResult(
                  await apiPost("/practice/submit", {
                    question_id: q.id,
                    selected_index: selected,
                  }),
                )
              }
            >
              Submit answer <ArrowRight size={16} />
            </button>
          )}
          {result && (
            <button className="secondary" onClick={load}>
              Next practice <ArrowRight size={16} />
            </button>
          )}
        </Card>
        <Card>
          <small>WHY THIS QUESTION?</small>
          <div className="bigStat">74%</div>
          <p className="muted">Current practice accuracy</p>
          <div className="statRows">
            <div>
              <b>42</b>
              <small>attempted</small>
            </div>
            <div>
              <b>31</b>
              <small>correct</small>
            </div>
            <div>
              <b>SQL</b>
              <small>priority</small>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}

function Interview() {
  const [q, setQ] = useState<any>(),
    [answer, setAnswer] = useState(""),
    [result, setResult] = useState<any>();
  useEffect(() => {
    apiGet("/interview/next").then(setQ);
  }, []);
  if (!q) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="STUDENT / MOCK INTERVIEW"
        title="Practice saying the answer."
        desc="Interview confidence comes from rehearsing technical reasoning, not memorizing scripts."
      />
      <Card className="interview">
        <div className="interviewMeta">
          <span>
            Question {q.question_index} of {q.total_questions}
          </span>
          <span>Project + behavioral</span>
        </div>
        <h2>{q.question}</h2>
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Write your answer as if you were speaking to an interviewer..."
        />
        {result && (
          <div className="feedback">
            <div className="scoreCircle">{result.feedback.overall_score}</div>
            <div>
              <h3>Interview feedback</h3>
              <p>{result.feedback.improvements.join(" ")}</p>
              <div className="feedbackTags">
                {result.feedback.strengths.map((x: string) => (
                  <Pill tone="green" key={x}>
                    <Check size={12} />
                    {x}
                  </Pill>
                ))}
              </div>
            </div>
          </div>
        )}
        <div className="actionRow">
          <button
            className="primary"
            disabled={!answer.trim()}
            onClick={async () =>
              setResult(await apiPost("/interview/submit", { answer }))
            }
          >
            {result ? "Re-score answer" : "Get feedback"} <Sparkles size={15} />
          </button>
        </div>
      </Card>
    </>
  );
}

function Resume() {
  const [file, setFile] = useState<File | null>(null),
    [role, setRole] = useState("Software Engineer"),
    [jd, setJd] = useState(""),
    [analysis, setAnalysis] = useState<ResumeAnalysis | null>(null),
    [history, setHistory] = useState<any[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const loadHistory = async () => {
    try {
      const data = await apiGet<any[]>("/resume/analyses");
      setHistory(Array.isArray(data) ? data : []);
    } catch {
      setHistory([]);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const analyze = async () => {
    if (!file) {
      setError("Please choose your resume first.");
      return;
    }

    setBusy(true);
    setError("");
    setAnalysis(null);

    const form = new FormData();
    form.append("resume", file);
    form.append("target_role", role.trim() || "Software Engineer");
    form.append("job_description", jd);

    try {
      const r = await apiUpload<ResumeAnalysis>("/resume/analyze", form);
      setAnalysis(r);

      try {
        const updatedHistory = await apiGet<any[]>("/resume/analyses");
        setHistory(Array.isArray(updatedHistory) ? updatedHistory : []);
      } catch {
        // The analysis itself succeeded; history refresh is optional.
      }
    } catch (e: any) {
      console.error("Resume analysis failed:", e);
      const detail = e?.body?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : e?.message ||
              "Resume analysis failed. Make sure the API is running and use a PDF, DOCX, TXT or MD file under 6 MB.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHead
        eyebrow="STUDENT / RESUME AI"
        title="Turn your resume into stronger evidence."
        desc="Upload your resume and Preceptron checks structure, impact, ATS alignment, role fit and the exact changes worth making."
        action={
          <Pill tone="green">
            <Sparkles size={12} /> AI-powered
          </Pill>
        }
      />
      <div className="resumeGrid">
        <Card className="uploadCard">
          <div className="uploadIcon">
            <UploadCloud />
          </div>
          <h2>Resume intelligence</h2>
          <p className="muted">PDF, DOCX, TXT or MD · up to 6 MB</p>
          <input
            ref={input}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            hidden
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setError("");
              setAnalysis(null);
            }}
          />
          <button
            type="button"
            className="dropzone"
            onClick={() => input.current?.click()}
          >
            <FileSearch size={22} />
            <b>{file ? file.name : "Choose your resume"}</b>
            <small>{file ? "Ready to analyze" : "Click to upload"}</small>
          </button>
          <label>
            Target role
            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="e.g. Software Engineer"
            />
          </label>
          <label>
            Optional job description
            <textarea
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              placeholder="Paste the job description for keyword and relevance matching..."
            />
          </label>
          {error && (
            <div className="error">
              <AlertTriangle size={16} />
              {error}
            </div>
          )}
          <button
            type="button"
            className="primary wide"
            disabled={!file || busy}
            onClick={analyze}
          >
            {busy ? (
              <>
                <span className="miniSpinner" /> Analyzing...
              </>
            ) : (
              <>
                Analyze my resume <Sparkles size={16} />
              </>
            )}
          </button>
          <div className="privacyNote">
            <ShieldCheck size={15} /> Your resume is processed by this app. Only
            use the optional external AI provider when you choose to enable it.
          </div>
        </Card>
        {analysis ? (
          <ResumeResult analysis={analysis} />
        ) : (
          <Card className="emptyResume">
            <div className="emptyIcon">
              <Brain />
            </div>
            <h2>Your recommendations will appear here</h2>
            <p className="muted">
              You'll get a score, strengths, gaps, ATS keyword alignment and
              concrete rewrite examples — not generic resume advice.
            </p>
            <div className="featureList">
              <span>
                <CheckCircle2 /> Structure check
              </span>
              <span>
                <Target /> Role alignment
              </span>
              <span>
                <Zap /> Impact bullets
              </span>
              <span>
                <FileSearch /> ATS keywords
              </span>
            </div>
          </Card>
        )}
      </div>
      <Card className="resumeHistory">
        <div className="sectionTitle">
          <h2>Recent analyses</h2>
          <span className="muted">{history.length} saved</span>
        </div>
        {history.length ? (
          history.map((x) => (
            <div className="historyRow" key={x.id}>
              <FileText size={17} />
              <div>
                <b>{x.filename}</b>
                <small>{x.role}</small>
              </div>
              <Pill
                tone={
                  x.score >= 75 ? "green" : x.score >= 60 ? "indigo" : "amber"
                }
              >
                {x.score}/100
              </Pill>
            </div>
          ))
        ) : (
          <p className="muted">Your analyzed resumes will be saved here.</p>
        )}
      </Card>
    </>
  );
}

function ResumeResult({ analysis }: { analysis: ResumeAnalysis }) {
  const r = analysis.result;
  return (
    <div className="resumeResult">
      <Card className="resumeScore">
        <small>RESUME READINESS</small>
        <div className="resumeScoreRow">
          <div className="scoreCircle large">{r.score}</div>
          <div>
            <h2>{r.summary}</h2>
            <p className="muted">
              {r.word_count} words · {r.engine.replace(/-/g, " ")}
            </p>
          </div>
        </div>
        <Progress value={r.score} />
      </Card>
      <Card>
        <h2>What is already working</h2>
        <div className="resultList">
          {r.strengths.map((x) => (
            <div key={x}>
              <CheckCircle2 />
              {x}
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <h2>Highest-impact changes</h2>
        <div className="resultList numbered">
          {r.suggestions.map((x, i) => (
            <div key={x}>
              <b>{i + 1}</b>
              <span>{x}</span>
            </div>
          ))}
        </div>
      </Card>
      <div className="resultCols">
        <Card>
          <h2>ATS keywords</h2>
          <small>MATCHED</small>
          <div className="keywordList">
            {r.ats_keywords_matched.map((x) => (
              <Pill tone="green" key={x}>
                {x}
              </Pill>
            ))}
          </div>
          <small>MISSING / CONSIDER</small>
          <div className="keywordList">
            {r.ats_keywords_missing.map((x) => (
              <Pill tone="amber" key={x}>
                {x}
              </Pill>
            ))}
          </div>
        </Card>
        <Card>
          <h2>Rewrite examples</h2>
          {r.rewrites.map((x) => (
            <div className="rewrite" key={x.after}>
              <small>BEFORE</small>
              <p>{x.before}</p>
              <small>STRONGER</small>
              <p className="stronger">{x.after}</p>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

function Analytics() {
  const [d, setD] = useState<any>();
  useEffect(() => {
    apiGet("/analytics").then(setD);
  }, []);
  if (!d) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="STUDENT / ANALYTICS"
        title="See the trajectory."
        desc="Readiness is useful when you can see what is moving it."
      />
      <div className="analyticsGrid">
        <Card>
          <small>READINESS TREND</small>
          <div className="chart">
            <div className="chartLine">
              {d.assessment_history.map((x: any) => (
                <span key={x.created_at} style={{ height: `${x.score}%` }} />
              ))}
            </div>
            <div className="chartLabels">
              {d.assessment_history.map((x: any) => (
                <span key={x.created_at}>{x.created_at.slice(5)}</span>
              ))}
            </div>
          </div>
        </Card>
        <Card>
          <small>READINESS FORMULA</small>
          <h3 className="formula">Assessment + skills + practice + roadmap</h3>
          <p className="muted">{d.disclaimer}</p>
          <div className="formulaBox">
            <span>Current</span>
            <b>{d.readiness_score}/100</b>
            <span>Roadmap</span>
            <b>{d.roadmap_progress}%</b>
          </div>
        </Card>
      </div>
      <div className="skillGrid">
        {d.skill_scores.map((s: SkillScore) => (
          <Card key={s.category}>
            <div className="skillHead">
              <b>{s.category}</b>
              <strong>{s.score}</strong>
            </div>
            <Progress value={s.score} />
            <small>{s.label}</small>
          </Card>
        ))}
      </div>
    </>
  );
}

function Profile() {
  const [d, setD] = useState<any>();
  useEffect(() => {
    apiGet("/profile").then(setD);
  }, []);
  if (!d) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="STUDENT / PROFILE"
        title="Your placement context."
        desc="Keep your target role and baseline current so recommendations stay relevant."
      />
      <Card className="profile">
        <div className="profileAvatar">{d.name[0]}</div>
        <div className="profileFields">
          <div>
            <small>NAME</small>
            <b>{d.name}</b>
          </div>
          <div>
            <small>COLLEGE</small>
            <b>{d.college || "Add your college"}</b>
          </div>
          <div>
            <small>BRANCH</small>
            <b>{d.branch}</b>
          </div>
          <div>
            <small>GRADUATION</small>
            <b>{d.graduation_year}</b>
          </div>
          <div>
            <small>TARGET ROLE</small>
            <b>{d.target_role}</b>
          </div>
          <div>
            <small>LEVEL</small>
            <b>{d.current_skill_level}</b>
          </div>
        </div>
      </Card>
    </>
  );
}

function Tpo({
  type,
}: {
  type: "dashboard" | "gaps" | "students" | "settings";
}) {
  const [d, setD] = useState<TpoSummary>();
  useEffect(() => {
    apiGet<TpoSummary>("/tpo/summary").then(setD);
  }, []);
  if (!d) return <Loading />;
  if (type === "settings")
    return (
      <>
        <PageHead
          eyebrow="TPO / SETTINGS"
          title="Workspace settings"
          desc="Keep cohort configuration simple while the MVP is validated."
        />
        <Card>
          <div className="emptyIcon">
            <Settings />
          </div>
          <h2>Settings are ready to extend</h2>
          <p className="muted">
            Current workspace is configured for aggregate cohort insights. Add
            branch, batch and role filters as the institution onboards more
            cohorts.
          </p>
        </Card>
      </>
    );
  if (type === "gaps")
    return (
      <>
        <PageHead
          eyebrow="TPO / SKILL GAPS"
          title="Skill gap analysis"
          desc="See which capabilities need the most cohort support."
        />
        <Card>
          <h2>Top areas needing attention</h2>
          {d.top_skill_gaps.map((g) => (
            <div className="largeGap" key={g.category}>
              <div>
                <b>{g.category}</b>
                <Progress value={Math.min(100, g.students / 2)} />
              </div>
              <Pill tone="amber">{g.students} students</Pill>
            </div>
          ))}
        </Card>
      </>
    );
  if (type === "students")
    return (
      <>
        <PageHead
          eyebrow="TPO / STUDENTS"
          title="Student overview"
          desc="Aggregate-only cohort visibility. Individual student records remain private."
        />
        <Card>
          <h2>Cohort roster summary</h2>
          <div className="statGrid mini">
            {[
              ["Students tracked", d.total_students],
              ["Graduation years", d.filters.graduation_years.length],
              ["Target roles", d.filters.target_roles.length],
            ].map((x) => (
              <div className="miniStat" key={x[0] as string}>
                <small>{x[0]}</small>
                <b>{x[1]}</b>
              </div>
            ))}
          </div>
        </Card>
      </>
    );
  return (
    <>
      <PageHead
        eyebrow="TPO / ADMIN"
        title="Cohort readiness"
        desc="Aggregated trends only. No unnecessary student-level personal information is shown."
      />
      <div className="statGrid">
        {[
          ["Total students", d.total_students, Users],
          ["Average readiness", `${d.average_readiness}%`, BarChart3],
          ["Roadmap completion", `${d.roadmap_completion}%`, ShieldCheck],
          ["Need support", d.students_needing_support, AlertTriangle],
        ].map(([n, v, I], idx) => {
          const Icon = I as any;
          return (
            <Card
              key={n as string}
              className={idx === 0 ? "darkCard" : idx === 3 ? "warnCard" : ""}
            >
              <Icon size={20} />
              <small>{n as ReactNode}</small>
              <b className="statNumber">{v as ReactNode}</b>
            </Card>
          );
        })}
      </div>
      <div className="twoCol">
        <Card>
          <h2>Top skill gaps</h2>
          {d.top_skill_gaps.map((g) => (
            <div className="gapRow" key={g.category}>
              <b>{g.category}</b>
              <Pill tone="amber">{g.students} students</Pill>
            </div>
          ))}
        </Card>
        <Card>
          <h2>Available filters</h2>
          <div className="filterGrid">
            <div>
              <small>BRANCHES</small>
              <b>{d.filters.branches.length} tracked</b>
            </div>
            <div>
              <small>GRAD YEARS</small>
              <b>{d.filters.graduation_years.join(", ")}</b>
            </div>
            <div>
              <small>TARGET ROLES</small>
              <b>{d.filters.target_roles.length} tracked</b>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}

function PitchLanding() {
  return (
    <div className="pitchPage">
      <header className="pitchNav">
        <Link to="/pitch" className="brand">
          <div className="brandMark">P</div>
          <div>
            <b>Preceptron</b>
            <small>Placement intelligence</small>
          </div>
        </Link>
        <Link to="/login" className="primary">
          Open live demo <ArrowRight size={15} />
        </Link>
      </header>
      <section className="pitchHero">
        <div>
          <Pill tone="green">IDEA PITCH · AI-ASSISTED PLACEMENT READINESS</Pill>
          <h1>
            From “What is my score?” to <span>“What should I do next?”</span>
          </h1>
          <p>
            Preceptron connects assessment, diagnosis, daily action, interview
            practice and resume intelligence into one closed-loop placement
            preparation system.
          </p>
          <div className="pitchActions">
            <Link to="/login" className="primary">
              Try the student demo <ArrowRight size={16} />
            </Link>
            <Link to="/login" className="secondary">
              Open TPO dashboard
            </Link>
          </div>
        </div>
        <div className="pitchMock">
          <div className="mockTop">
            <span>READINESS</span>
            <Pill>On track</Pill>
          </div>
          <div className="mockScore">
            71<span>/100</span>
          </div>
          <Progress value={71} />
          <div className="mockAction">
            <Sparkles size={16} />
            <div>
              <small>NEXT BEST ACTION</small>
              <b>Close your SQL gap</b>
            </div>
          </div>
        </div>
      </section>
      <section className="pitchSection">
        <div className="pitchSectionHead">
          <div className="eyebrow">THE PROBLEM</div>
          <h2>Placement preparation is fragmented.</h2>
          <p>
            Students collect scores, practice randomly, rewrite resumes
            separately and often do not know which action has the highest
            expected value.
          </p>
        </div>
        <div className="problemGrid">
          <Card>
            <Target />
            <h3>Too much signal</h3>
            <p>
              Assessments tell students where they stand, but not always what to
              do next.
            </p>
          </Card>
          <Card>
            <GitFork />
            <h3>No action loop</h3>
            <p>
              Preparation tools rarely connect diagnosis to a personalized
              weekly plan.
            </p>
          </Card>
          <Card>
            <FileText />
            <h3>Resume is disconnected</h3>
            <p>
              Resume quality, role fit and skill gaps should reinforce the same
              preparation strategy.
            </p>
          </Card>
        </div>
      </section>
      <section className="pitchSection darkPitch">
        <div className="eyebrow">THE SOLUTION</div>
        <h2>Measure → Diagnose → Act → Re-measure</h2>
        <div className="pitchLoop">
          <div>
            <b>01</b>
            <strong>Measure</strong>
            <span>Assess skills and readiness.</span>
          </div>
          <div>
            <b>02</b>
            <strong>Diagnose</strong>
            <span>Find the highest-impact gaps.</span>
          </div>
          <div>
            <b>03</b>
            <strong>Act</strong>
            <span>Generate targeted tasks, practice and interview drills.</span>
          </div>
          <div>
            <b>04</b>
            <strong>Re-measure</strong>
            <span>Track movement and adapt the plan.</span>
          </div>
        </div>
      </section>
      <section className="pitchSection">
        <div className="eyebrow">WHY IT CAN SCALE</div>
        <h2>One learner loop, two sides of the institution.</h2>
        <div className="scaleGrid">
          <Card>
            <ShieldCheck />
            <h3>Student intelligence</h3>
            <p>
              Personal readiness, skill gaps, roadmap, practice, mock interviews
              and AI resume feedback.
            </p>
          </Card>
          <Card>
            <Users />
            <h3>TPO intelligence</h3>
            <p>
              Aggregate readiness, skill-gap concentration and support demand
              without exposing unnecessary student-level data.
            </p>
          </Card>
          <Card>
            <Brain />
            <h3>AI augmentation</h3>
            <p>
              Use AI where judgment is expensive: resume feedback, interview
              coaching and next-action recommendations.
            </p>
          </Card>
        </div>
      </section>
      <footer className="pitchFooter">
        <div>
          <b>Preceptron</b>
          <span>Know what to improve. Know what to do next.</span>
        </div>
        <Link to="/login" className="primary">
          Launch demo <ArrowRight size={15} />
        </Link>
      </footer>
    </div>
  );
}

function App() {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [checking, setChecking] = useState(true);
  const nav = useNavigate();
  useEffect(() => {
    apiGet<UserPublic>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);
  const logout = async () => {
    try {
      await apiPost("/auth/logout");
    } finally {
      setUser(null);
      nav("/login");
    }
  };
  if (checking) return <Loading />;
  const protectedPage = (page: ReactNode) =>
    user ? (
      <Shell user={user} onLogout={logout}>
        {page}
      </Shell>
    ) : (
      <Navigate to="/login" replace />
    );
  return (
    <Routes>
      <Route path="/pitch" element={<PitchLanding />} />
      <Route
        path="/login"
        element={
          user ? (
            <Navigate
              to={user.role === "tpo" ? "/tpo" : "/dashboard"}
              replace
            />
          ) : (
            <Login onLogin={setUser} />
          )
        }
      />
      <Route path="/dashboard" element={protectedPage(<Dashboard />)} />
      <Route path="/assessment" element={protectedPage(<Assessment />)} />
      <Route path="/roadmap" element={protectedPage(<Roadmap />)} />
      <Route path="/practice" element={protectedPage(<Practice />)} />
      <Route path="/mock-interview" element={protectedPage(<Interview />)} />
      <Route path="/resume" element={protectedPage(<Resume />)} />
      <Route path="/analytics" element={protectedPage(<Analytics />)} />
      <Route path="/profile" element={protectedPage(<Profile />)} />
      <Route path="/tpo" element={protectedPage(<Tpo type="dashboard" />)} />
      <Route
        path="/tpo/skill-gaps"
        element={protectedPage(<Tpo type="gaps" />)}
      />
      <Route
        path="/tpo/students"
        element={protectedPage(<Tpo type="students" />)}
      />
      <Route
        path="/tpo/settings"
        element={protectedPage(<Tpo type="settings" />)}
      />
      <Route
        path="/"
        element={
          <Navigate
            to={user ? (user.role === "tpo" ? "/tpo" : "/dashboard") : "/pitch"}
            replace
          />
        }
      />
      <Route
        path="*"
        element={
          <Navigate
            to={user ? (user.role === "tpo" ? "/tpo" : "/dashboard") : "/pitch"}
            replace
          />
        }
      />
    </Routes>
  );
}
export default function Root() {
  // Issue 1: fire-and-forget health ping to wake the Render backend.
  // Runs once after mount; does NOT block rendering or show a loader.
  useEffect(() => {
    const apiBase = (
      import.meta.env.VITE_API_URL ||
      (import.meta.env.DEV ? "/api" : "http://127.0.0.1:8001/api")
    ).replace(/\/$/, "");
    fetch(`${apiBase}/health`, { method: "GET", credentials: "include" }).catch(
      () => {},
    );
  }, []);

  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  );
}
