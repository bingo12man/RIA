import { useEffect, useState } from "react";
import "./App.css";

const modes = {
  idle: "I'm here whenever you need me!",
  listening: "I'm listening...",
  thinking: "Hmm, let me think!",
  speaking: "Here's what I think!",
  happy: "Yayyy! We did it!",
};

export default function App() {
  const [mode, setMode] = useState("idle");
  const [message, setMessage] = useState("");
  const [chat, setChat] = useState([]);
  const [quiet, setQuiet] = useState(false);

  const [reminder, setReminder] = useState(null);
  const [reminderError, setReminderError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    async function checkReminders() {
      if (quiet) return;

      try {
        const response = await fetch("/api/reminders/due");
        if (!response.ok) throw new Error("Reminder API unavailable");

        const due = await response.json();
        setReminder((current) => {
          // Keep showing the current reminder until handled.
          if (current) return current;
          return due.length > 0 ? due[0] : null;
        });
        setReminderError("");
      } catch {
        setReminderError("Reminder service is offline.");
      }
    }

    checkReminders();
    const interval = setInterval(checkReminders, 5000);

    return () => clearInterval(interval);
  }, [quiet]);

  async function handleReminder(action) {
    if (!reminder || busy) return;

    setBusy(true);
    setReminderError("");

    try {
      const url = `/api/reminders/${reminder.id}/${action}`;
      const options = { method: "POST" };

      if (action === "snooze") {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify({ minutes: 5 });
      }

      const response = await fetch(url, options);
      if (!response.ok) throw new Error("Could not update reminder");

      setReminder(null);

      if (action === "done") {
        setMode("happy");
      } else {
        setMode("idle");
      }
    } catch {
      setReminderError("Couldn't update reminder. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function sendMessage(e) {
    e.preventDefault();
    const text = message.trim();
    if (!text) return;

    setChat((old) => [
      ...old,
      { role: "you", text },
      {
        role: "ria",
        text: "Hehe! My chat brain isn't connected to this screen yet. But I'm ready for our next adventure!",
      },
    ]);

    setMessage("");
    setMode("happy");
  }

  return (
    <main className="app">
      <div className="shell">
        <header className="header">
          <div>
            <span className="eyebrow">YOUR LITTLE DESK BUDDY</span>
            <h1>RIA <span className="sparkle">✦</span></h1>
          </div>

          <button
            className="quiet-btn"
            onClick={() => setQuiet((old) => !old)}
            aria-pressed={quiet}
          >
            {quiet ? "Quiet mode on" : "Quiet mode off"}
          </button>
        </header>

        <section className="companion" aria-label="RIA animated companion">
          <div className={`face ${mode}`} aria-hidden="true">
            <div className="eyes">
              <div className="eye" />
              <div className="eye" />
            </div>
            <div className="mouth" />
            <div className="blush blush-left" />
            <div className="blush blush-right" />
          </div>

          <div className="mode-label" role="status">
            <span className="status-dot" />
            {mode.toUpperCase()}
          </div>

          <p className="ria-text">{modes[mode]}</p>
        </section>

        <section className="panel" aria-label="RIA expressions">
          <h2>Meet Ria's moods</h2>
          <div className="mood-buttons">
            {Object.keys(modes).map((value) => (
              <button
                key={value}
                className={mode === value ? "selected" : ""}
                onClick={() => setMode(value)}
                aria-pressed={mode === value}
              >
                {value.charAt(0).toUpperCase() + value.slice(1)}
              </button>
            ))}
          </div>
        </section>

        <section className="panel" aria-label="Text chat preview">
          <h2>Talk to Ria <span className="tag">UI demo</span></h2>

          <div className="messages" role="log" aria-live="polite">
            {chat.length === 0 ? (
              <p className="muted">Say hello! AI chat will be connected later.</p>
            ) : (
              chat.map((item, i) => (
                <div key={i} className={`bubble ${item.role}`}>
                  <strong>{item.role === "you" ? "You" : "RIA"}</strong>
                  <p>{item.text}</p>
                </div>
              ))
            )}
          </div>

          <form onSubmit={sendMessage} className="chat-form">
            <input
              aria-label="Message to Ria"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="What's on your mind?"
            />
            <button type="submit">Send</button>
          </form>
        </section>

        <section className="panel reminder-panel">
          <div>
            <h2>Smart reminders <span className="tag">Connected</span></h2>
            <p className="muted">
              {quiet
                ? "Quiet mode is on. Reminder notifications are paused."
                : "RIA checks for due reminders every 5 seconds."}
            </p>
            {reminderError && (
              <p role="alert">{reminderError}</p>
            )}
          </div>
        </section>

        {reminder && !quiet && (
          <section className="reminder-alert" role="alert">
            <strong>🔔 Psst! RIA has a reminder for you!</strong>
            <p>{reminder.title}</p>

            <div className="alert-actions">
              <button
                disabled={busy}
                onClick={() => handleReminder("done")}
              >
                Done!
              </button>
              <button
                disabled={busy}
                onClick={() => handleReminder("snooze")}
              >
                Snooze 5 min
              </button>
              <button
                disabled={busy}
                onClick={() => handleReminder("skip")}
              >
                Skip
              </button>
            </div>
          </section>
        )}

        <footer>
          Local prototype · Real reminders · No GPU inference
        </footer>
      </div>
    </main>
  );
}
