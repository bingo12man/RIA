import { useEffect, useRef, useState } from "react";
import "./App.css";
import RiaLotus from "./RiaLotus";
import "./NeonOrbit.css";

const API = "/api/reminders";

export default function App() {
  const [neonPanel, setNeonPanel] = useState("talk");
  const [reminder, setReminder] = useState(null);
  const [reminderOpen, setReminderOpen] = useState(false);
  const [quiet, setQuiet] = useState(false);
  const [recording, setRecording] = useState(false);
  const [mood, setMood] = useState("idle");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioRef = useRef(null);
  const speechAudioRef = useRef(null);
  const speechCancelRef = useRef(null);

  const notifiedIdsRef = useRef(new Set());
  const quietRef = useRef(false);
  const processingRef = useRef(false);
  const [processing, setProcessing] = useState(false);
  // Keeps recent conversations in the same Ollama session.
  const conversationSessionRef = useRef(null);
  const nativeSessionRef = useRef(null);


  quietRef.current = quiet;

  async function enableAudio() {
    try {
      const AudioClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioClass) return;

      if (!audioRef.current) audioRef.current = new AudioClass();
      if (audioRef.current.state === "suspended") {
        await audioRef.current.resume();
      }
    } catch (err) {
      console.warn("Audio unavailable:", err);
    }
  }

  function chime() {
    const ctx = audioRef.current;
    if (!ctx || ctx.state !== "running") return;

    [660, 880].forEach((frequency, index) => {
      const start = ctx.currentTime + index * 0.18;
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();

      oscillator.type = "sine";
      oscillator.frequency.value = frequency;

      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.07, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.28);

      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.3);
    });
  }

  // Poll the existing FastAPI service for scheduled reminders.
  useEffect(() => {
    let active = true;

    async function checkDue() {
      try {
        const response = await fetch(`${API}/due`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Reminder API unavailable");

        const due = await response.json();
        if (!active) return;

        setError("");

        const first = due[0] || null;
        setReminder(first);

        // Alert once per reminder, not every five seconds.
        if (
          first &&
          !quietRef.current &&
          !notifiedIdsRef.current.has(first.id)
        ) {
          notifiedIdsRef.current.add(first.id);
          setNotice("Psst! You have a reminder!");
          chime();
        }
      } catch {
        if (active) setError("Reminder service offline");
      }
    }

    checkDue();
    const interval = setInterval(checkDue, 5000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (recording) {
      setMood("listening");
    } else if (quiet) {
      setMood("sleepy");
    } else if (reminder) {
      setMood("curious");
    } else {
      setMood("idle");
    }
  }, [recording, quiet, reminder]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    return () => {
      if (recorderRef.current?.state === "recording") {
        recorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, []);

  async function handleReminder(action) {
    if (!reminder || busy) return;

    setBusy(true);

    try {
      const options = { method: "POST" };

      if (action === "snooze") {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify({ minutes: 5 });
      }

      const response = await fetch(
        `${API}/${reminder.id}/${action}`,
        options
      );

      if (!response.ok) throw new Error("Update failed");

      setReminder(null);
      setReminderOpen(false);

      if (action === "done") {
        setNotice("Yay! Nicely done!");
      } else if (action === "snooze") {
        setNotice("Okay, five more minutes!");
      } else {
        setNotice("No worries!");
      }
    } catch {
      setError("Couldn't update reminder.");
    } finally {
      setBusy(false);
    }
  }


  // RIA_P043_STOP_BUTTON
  function handleStopRIA() {
    stopSpeech();
    setNotice("Stopped.");
    setMood(quietRef.current ? "sleepy" : "idle");
    console.log("RIA speech interrupted by user.");
  }

  function stopSpeech() {
    // Cancel the active playback promise, if any.
    speechCancelRef.current?.();
    speechCancelRef.current = null;

    const audio = speechAudioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
      speechAudioRef.current = null;
    }
  }

  // RIA P0.4.3: Clean Markdown and prepare spoken text.
  function prepareSpeechText(text) {
    return String(text || "")
      .replace(/```[\s\S]*?```/g, " Code example omitted from speech. ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/__(.*?)__/g, "$1")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/^\s*[-*]\s+/gm, "Next, ")
      .replace(/^\s*\d+[.)]\s+/gm, "Step: ")
      .replace(/\n+/g, " ")
      .replace(/(?:\.\s*){2,}/g, ".")
      .replace(/\s+/g, " ")
      .trim();
  }

  // Keep every TTS request safely below the 500-character limit.
  function splitSpeechChunks(text, maxLength = 380) {
    const sentences =
      text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [];

    const chunks = [];
    let current = "";

    function pushCurrent() {
      if (current.trim()) chunks.push(current.trim());
      current = "";
    }

    for (const sentence of sentences) {
      const words = sentence.trim().split(/\s+/).filter(Boolean);

      for (const word of words) {
        // Handle unusually long unbroken strings safely.
        if (word.length > maxLength) {
          pushCurrent();
          for (let i = 0; i < word.length; i += maxLength) {
            chunks.push(word.slice(i, i + maxLength));
          }
          continue;
        }

        const next = current ? `${current} ${word}` : word;

        if (next.length > maxLength) {
          pushCurrent();
          current = word;
        } else {
          current = next;
        }
      }

      // Prefer sentence boundaries when reasonable.
      if (current.length >= 180) {
        pushCurrent();
      }
    }

    pushCurrent();
    return chunks;
  }

  async function speakReply(text) {
    if (!text?.trim() || quietRef.current) return;

    stopSpeech();

    const speechText = prepareSpeechText(text);
    const chunks = splitSpeechChunks(speechText);

    if (!chunks.length) return;

    const totalStart = performance.now();
    const controller = new AbortController();
    let cancelled = false;
    let activeAudio = null;
    let finishPlayback = null;

    const cancelThisSpeech = () => {
      cancelled = true;
      controller.abort();

      if (activeAudio) {
        activeAudio.pause();
        activeAudio.currentTime = 0;
      }

      finishPlayback?.();
    };

    // Keep cancellation available during synthesis AND playback.
    speechCancelRef.current = cancelThisSpeech;

    setMood("thinking");
    setNotice("Preparing my voice...");

    console.log("RIA original reply:", text);
    console.log("RIA prepared speech:", speechText);
    console.log(
      "RIA spoken word count:",
      speechText.split(/\s+/).length
    );
    console.log("RIA speech chunks:", chunks.length);

    try {
      for (let index = 0; index < chunks.length; index++) {
        if (cancelled || quietRef.current) break;

        const chunk = chunks[index];
        const ttsStart = performance.now();

        console.log(
          `RIA chunk ${index + 1}/${chunks.length}:`,
          chunk
        );

        const response = await fetch("/api/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: chunk,
            language: "english"
          }),
          signal: controller.signal
        });

        const headersReceivedAt = performance.now();

        if (!response.ok) {
          throw new Error(
            `TTS failed on chunk ${index + 1}: ${response.status}`
          );
        }

        const blob = await response.blob();
        const blobReadyAt = performance.now();

        console.log(
          `RIA TTS HTTP headers: ${
            ((headersReceivedAt - ttsStart) / 1000).toFixed(3)
          }s`
        );

        console.log(
          `RIA TTS body transfer: ${
            ((blobReadyAt - headersReceivedAt) / 1000).toFixed(3)
          }s`
        );

        if (cancelled || quietRef.current) break;

        console.log(
          `RIA chunk ${index + 1} TTS: ` +
          `${((performance.now() - ttsStart) / 1000).toFixed(2)}s`
        );

        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        activeAudio = audio;
        speechAudioRef.current = audio;

        const ctx = audioRef.current;
        const face = document.querySelector(".ria-face");

        let analyser = null;
        let source = null;
        let lipFrame = null;
        let smoothedLevel = 0;

        try {
          if (ctx && ctx.state === "running") {
            analyser = ctx.createAnalyser();
            analyser.fftSize = 1024;
            analyser.smoothingTimeConstant = 0.35;

            source = ctx.createMediaElementSource(audio);
            source.connect(analyser);
            analyser.connect(ctx.destination);
          }

          const waveform = analyser
            ? new Uint8Array(analyser.fftSize)
            : null;

          function updateLips() {
            if (
              !analyser ||
              audio.paused ||
              cancelled ||
              quietRef.current
            ) return;

            analyser.getByteTimeDomainData(waveform);

            let energy = 0;

            for (let i = 0; i < waveform.length; i++) {
              const sample = (waveform[i] - 128) / 128;
              energy += sample * sample;
            }

            const rms = Math.sqrt(energy / waveform.length);
            const target = Math.max(
              0,
              Math.min(1, (rms - 0.018) * 10)
            );

            smoothedLevel =
              smoothedLevel * 0.55 + target * 0.45;

            face?.style.setProperty(
              "--ria-mouth-open",
              smoothedLevel.toFixed(3)
            );

            lipFrame = requestAnimationFrame(updateLips);
          }

          const playbackStart = performance.now();

          await new Promise((resolve, reject) => {
            let settled = false;

            const finish = () => {
              if (settled) return;
              settled = true;
              finishPlayback = null;
              resolve();
            };

            finishPlayback = finish;

            audio.onloadedmetadata = () => {
              console.log(
                `RIA chunk ${index + 1} audio duration:`,
                Number.isFinite(audio.duration)
                  ? `${audio.duration.toFixed(2)}s`
                  : "unknown"
              );
            };

            audio.onended = finish;

            audio.onerror = () => {
              if (cancelled) {
                finish();
              } else if (!settled) {
                settled = true;
                finishPlayback = null;
                reject(new Error("Audio playback failed"));
              }
            };

            if (cancelled || quietRef.current) {
              finish();
              return;
            }

            audio.play()
              .then(() => {
                if (cancelled || quietRef.current) {
                  finish();
                  return;
                }

                console.log(
                  `RIA chunk ${index + 1} playback started`
                );

                if (index === 0) {
                  console.log(
                    "RIA time to first audio from speech start:",
                    ((performance.now() - totalStart) / 1000).toFixed(3) + "s"
                  );
                }

                setMood("speaking");
                setNotice("Speaking...");

                if (analyser) {
                  lipFrame = requestAnimationFrame(updateLips);
                }
              })
              .catch(error => {
                if (cancelled) {
                  finish();
                } else if (!settled) {
                  settled = true;
                  finishPlayback = null;
                  reject(error);
                }
              });
          });

          console.log(
            `RIA chunk ${index + 1} playback stage: ` +
            `${((performance.now() - playbackStart) / 1000).toFixed(2)}s`
          );

        } finally {
          if (lipFrame !== null) {
            cancelAnimationFrame(lipFrame);
          }

          face?.style.removeProperty("--ria-mouth-open");

          audio.onloadedmetadata = null;
          audio.onended = null;
          audio.onerror = null;

          audio.pause();
          source?.disconnect();
          analyser?.disconnect();

          if (speechAudioRef.current === audio) {
            speechAudioRef.current = null;
          }

          if (activeAudio === audio) {
            activeAudio = null;
          }

          audio.removeAttribute("src");
          audio.load();
          URL.revokeObjectURL(url);
        }
      }

      if (!cancelled && !quietRef.current) {
        console.log(
          "RIA full speech stage:",
          `${((performance.now() - totalStart) / 1000).toFixed(2)}s`
        );
      }

    } catch (error) {
      if (!cancelled) throw error;

    } finally {
      if (speechCancelRef.current === cancelThisSpeech) {
        speechCancelRef.current = null;
      }

      if (!cancelled && !quietRef.current) {
        setMood("idle");
      }
    }
  }

  async function uploadAudio(blob) {
    if (processingRef.current) {
      console.log("RIA busy: ignoring duplicate recording.");
      return;
    }

    processingRef.current = true;
    setProcessing(true);
    const pipelineStart = performance.now();
    setMood("thinking");
    setNotice("Thinking...");

    try {
      const form = new FormData();
      const extension = blob.type.includes("mp4") ? "m4a" : "webm";

      form.append("file", blob, `ria-recording.${extension}`);

      // Step 1: Convert speech into text using Whisper.
      const transcriptionController = new AbortController();
      const transcriptionTimeout = setTimeout(
        () => transcriptionController.abort(),
        70000
      );

      let response;

      try {
        response = await fetch("/api/audio/transcribe", {
          method: "POST",
          body: form,
          signal: transcriptionController.signal,
        });
      } finally {
        clearTimeout(transcriptionTimeout);
      }

      if (!response.ok) {
        throw new Error(`Transcription failed: ${response.status}`);
      }

      const transcript = await response.json();

      console.table({
        "Audio conversion": transcript.conversion_seconds,
        "Modal roundtrip": transcript.modal_roundtrip_seconds,
        "Whisper inference": transcript.inference_seconds,
      });
      console.log(`RIA transcription: ${((performance.now() - pipelineStart) / 1000).toFixed(2)}s`);
      const commandStart = performance.now();
      console.log("RIA recognized speech:", transcript.text);

      if (!transcript.text?.trim()) {
        const noSpeech =
          transcript.silence_detected === true ||
          transcript.rejection_reason === "no_speech_activity";

        if (noSpeech) {
          setNotice("I didn't hear any speech.");
        } else {
          const clarification =
            "Sorry, I didn't catch that. Could you say it again, please?";

          setNotice(clarification);

          if (!quietRef.current) {
            try {
              await speakReply(clarification);
            } catch (speechError) {
              console.warn(
                "RIA clarification speech unavailable:",
                speechError
              );
            }
          }
        }

        setMood(quietRef.current ? "sleepy" : "idle");
        return;
      }

      // Handle explicit voice stop commands locally.
      // Never send these to the conversational LLM.
      const normalizedCommand = transcript.text
        .toLowerCase()
        .replace(/[.,!?]/g, "")
        .trim();

      if ([
        "stop",
        "stop talking",
        "stop speaking",
        "ria stop",
        "hey ria stop",
      ].includes(normalizedCommand)) {
        stopSpeech();
        setNotice("Stopped.");
        setMood(quietRef.current ? "sleepy" : "idle");
        return;
      }

      // RIA_PUNCTUATION_GUARD
      // Reject punctuation-only transcription from claps and noise.
      const meaningfulSpeech = (transcript.text || "")
        .trim()
        .replace(/[^\p{L}\p{N}]/gu, "");

      if (!meaningfulSpeech) {
        console.log("RIA ignored punctuation-only/noise transcript");
        setNotice("");
        setMood(quietRef.current ? "sleepy" : "idle");
        return;
      }

      // Step 2: Interpret and execute the command locally.
      // RIA_P16_INTERACTION_ID
      // Generate once per recognized voice interaction.
      // Reuse this ID if this command request is retried.
      const interactionId = crypto.randomUUID();

      const commandResponse = await fetch("/api/command", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: transcript.text,
          session_id: conversationSessionRef.current,
          native_session_id: nativeSessionRef.current,
          request_id: interactionId,
        }),
      });

      if (!commandResponse.ok) {
        throw new Error(`Command failed: ${commandResponse.status}`);
      }

      const result = await commandResponse.json();
      console.log(`RIA command + AI: ${((performance.now() - commandStart) / 1000).toFixed(2)}s`);
      const speechStart = performance.now();

      console.log("RIA command result:", result);

      // RIA_P181_MEMORY_SESSION_RESET
      // Successful memory changes must not reuse old chat history.
      const memoryChanged =
        result.success === true &&
        [
          "memory_saved",
          "memory_updated",
          "memory_deleted",
        ].includes(result.action);

      // RIA_HYBRID_NATIVE_SESSION
      if (result.native_reset_session === true ||
          result.reset_session === true ||
          memoryChanged) {
        nativeSessionRef.current = null;
      } else if ("native_session_id" in result) {
        nativeSessionRef.current = result.native_session_id;
      }

      if (result.reset_session === true || memoryChanged) {
        conversationSessionRef.current = null;
        console.log("RIA conversation session reset after completed state-changing action");
      } else if (result.session_id) {
        conversationSessionRef.current = result.session_id;
        console.log("RIA conversation session:", result.session_id);
      }

      // Step 3: Show RIA's response.
      if (result.action === "conversation") {
        setNotice("Getting my reply ready...");
      } else {
        setNotice(result.reply || "I heard you.");
      }

      // Speak confirmations after successful reminder actions.
      // Unrecognized conversation requests stay text-only for now.
      const canSpeak =
        result.reply &&
        !quietRef.current &&
        (
          result.success === true ||
          [
            "respond",
            "clarify",
            "reject",
            "duplicate_confirmation_required",
            "cancel_confirmation_required",
          ].includes(result.action)
        );

      if (canSpeak) {
        try {
          await speakReply(result.reply);
        console.log(`RIA speech stage: ${((performance.now() - speechStart) / 1000).toFixed(2)}s`);
        } catch (speechError) {
          console.warn("RIA speech playback unavailable:", speechError);
        }
      }

      if (quietRef.current) {
        setMood("sleepy");
      } else if (result.success) {
        setMood("happy");
      } else {
        setMood("curious");
      }

    } catch (error) {
      console.error("RIA voice command failed:", error);

      const recoveryMessage =
        error.name === "AbortError"
          ? "Sorry, my speech recognition took too long. Please try again."
          : error.message?.includes("Transcription failed")
            ? "Oops, I couldn't catch that. Could you say it again?"
            : error.message?.includes("503")
              ? "Oops, my AI service is busy right now. Please try again shortly."
            : "Sorry, I couldn't process that. Please try again.";

      setNotice(recoveryMessage);
      setMood(quietRef.current ? "sleepy" : "curious");

      if (!quietRef.current) {
        try {
          await speakReply(recoveryMessage);
        } catch (speechError) {
          console.warn(
            "RIA spoken error recovery unavailable:",
            speechError
          );
        }
      }
    } finally {
      console.log(`RIA total pipeline: ${((performance.now() - pipelineStart) / 1000).toFixed(2)}s`);
      processingRef.current = false;
      setProcessing(false);
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }

    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    setRecording(false);
  }

  async function toggleRecording() {
    if (processingRef.current) {
      // Allow barge-in only when speech cancellation is available.
      // Do not interrupt transcription or command execution.
      if (speechCancelRef.current) {
        speechCancelRef.current();
      } else {
        setNotice("One moment, I'm still thinking...");
        return;
      }
    }

    if (recording) {
      stopRecording();
      return;
    }

    if (quiet) return;

    // This user gesture also unlocks the browser chime.
    enableAudio();

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });

      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      const chunks = [];

      recorder.ondataavailable = event => {
        if (event.data.size) chunks.push(event.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(chunks, {
          type: recorder.mimeType,
        });

        console.log("RIA recorded audio:", {
          bytes: blob.size,
          type: blob.type,
        });

        if (blob.size > 0) {
          // Wait for the cancelled speech pipeline to release its
          // processing lock before submitting the new recording.
          void (async () => {
            for (let attempt = 0;
                 attempt < 100 && processingRef.current;
                 attempt++) {
              await new Promise(resolve => setTimeout(resolve, 50));
            }

            if (processingRef.current) {
              setNotice("Still finishing the previous request. Try again.");
              return;
            }

            await uploadAudio(blob);
          })();
        } else {
          setNotice("No audio captured");
        }

        recorderRef.current = null;
      };

      recorderRef.current = recorder;
      recorder.start();

      setRecording(true);
      setNotice("Listening...");
    } catch {
      streamRef.current?.getTracks().forEach(t => t.stop());
      streamRef.current = null;
      setRecording(false);
      setNotice("Please check microphone permission");
    }
  }

  function toggleQuiet() {
    enableAudio();
    if (recording) stopRecording();

    if (!quietRef.current) {
      // Silence RIA immediately when Quiet Mode is enabled.
      quietRef.current = true;
      stopSpeech();
      setMood("sleepy");
    }

    setQuiet(previous => !previous);
    setReminderOpen(false);
  }

  return (
    <main className="ria-app neon-app">
      <section className="ria-screen neon-screen" aria-label="RIA companion">
        <header className="neon-header">
          <span className="neon-wordmark">RIA <span>✦</span></span>
          <div className="neon-top-actions">
            <span className={`connection ${error ? "offline" : ""}`} title={error || "Reminder API connected"} />
            <span className="neon-clock" aria-label="Current time">
              {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
            <button type="button" className="neon-small-control" onClick={handleStopRIA} aria-label="Stop RIA speaking" title="Stop RIA speaking">■</button>
            <button type="button" className="neon-small-control" onClick={toggleQuiet} aria-label={quiet ? "Disable quiet mode" : "Enable quiet mode"} aria-pressed={quiet}>{quiet ? "☾" : "♫"}</button>
          </div>
        </header>

        <div className="neon-dashboard">
          <div className="neon-character-area">
            <div className="neon-character-halo" aria-hidden="true" />
            <RiaLotus mood={mood} recording={recording} processing={processing} quiet={quiet} reminder={reminder} />
            <div className="neon-character-name">R I A</div>
            <p className="neon-character-caption">Your little universe of help</p>
          </div>

          <div className="neon-content-area">
            <div className="neon-greeting">
              <h1>Hi <span>Kiran!</span><span className="neon-sparkle">✦</span></h1>
              <p>{quiet ? "Taking a little rest." : recording ? "I’m listening to you." : processing ? "Thinking about that…" : "Let’s make today count. ☀️"}</p>
            </div>
            <section className="neon-reminders" aria-label="Reminder preview">
              <div className="neon-section-label"><span>✧</span> REMINDERS</div>
              {reminder ? (
                <button type="button" className="neon-reminder-row" onClick={() => { enableAudio(); setReminderOpen(open => !open); }} aria-expanded={reminderOpen}>
                  <span className="neon-reminder-icon">◷</span><span className="neon-reminder-title">{reminder.title}</span><span className="neon-reminder-tag">Due now</span><span aria-hidden="true">›</span>
                </button>
              ) : (
                <div className="neon-reminders-empty">No reminders due right now. Ask RIA to set one!</div>
              )}
            </section>

            <p className="neon-status" role="status">{quiet ? "Resting…" : recording ? "Listening… tap again to stop" : reminder ? "You have a reminder!" : notice || (processing ? "Working on your request…" : "Here with you ♡")}</p>

            <div className="neon-features" aria-label="RIA features">
              <button type="button" className="neon-feature talk" onClick={() => setNeonPanel("talk")} aria-pressed={neonPanel === "talk"}><span className="neon-feature-icon">♧</span><span>Talk</span></button>
              <button type="button" className="neon-feature reminders" onClick={() => { setNeonPanel("reminders"); if (reminder) setReminderOpen(true); }} aria-pressed={neonPanel === "reminders"}><span className="neon-feature-icon">▦</span><span>Reminders</span></button>
              <button type="button" className="neon-feature recipes" onClick={() => setNeonPanel("recipes")} aria-pressed={neonPanel === "recipes"}><span className="neon-feature-icon">♨</span><span>Recipes</span></button>
              <button type="button" className="neon-feature outfit" onClick={() => setNeonPanel("outfit")} aria-pressed={neonPanel === "outfit"}><span className="neon-feature-icon">♢</span><span>Outfit</span></button>
            </div>
            <div className="neon-panel-copy" aria-live="polite">
              {neonPanel === "talk" && "Tap the microphone and talk to RIA."}
              {neonPanel === "reminders" && (reminder ? "Tap the reminder above to manage it, or ask RIA to set another." : "Ask RIA to create or check a reminder.")}
              {neonPanel === "recipes" && "Ask RIA what to cook or to guide you through a recipe."}
              {neonPanel === "outfit" && "Ask RIA for an outfit idea. Dedicated wardrobe features are coming later."}
            </div>
          </div>

          <div className="neon-mic-area">
            {!quiet && <>
              <button type="button" className={`mic-button neon-mic ${recording ? "is-recording" : ""} ${processing ? "is-processing" : ""}`} onClick={toggleRecording} disabled={processing && !speechCancelRef.current} aria-label={recording ? "Stop recording" : processing && speechCancelRef.current ? "Interrupt RIA and start recording" : processing ? "RIA is thinking" : "Start recording"} aria-pressed={recording}>
                <svg viewBox="0 0 24 24" width="70" height="70" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5m-4 0h8"/></svg>
              </button>
              <span className="neon-mic-hint">{recording ? "Tap to stop" : "Tap to talk"}</span>
            </>}
            {quiet && <p className="neon-quiet">Quiet mode is on</p>}
          </div>
        </div>

        {reminder && !quiet && reminderOpen && (
          <section className="reminder-overlay neon-overlay" aria-label="Due reminder">
            <span className="reminder-label">✦ REMINDER</span>
            <p className="reminder-title">{reminder.title}</p>
            <div className="reminder-actions">
              <button className="primary" disabled={busy} onClick={() => handleReminder("done")}>✓ Done</button>
              <button disabled={busy} onClick={() => handleReminder("snooze")}>Later</button>
              <button disabled={busy} onClick={() => handleReminder("skip")}>Skip</button>
            </div>
            <button type="button" className="neon-dismiss" onClick={() => setReminderOpen(false)}>Close</button>
          </section>
        )}
        {error && <p className="error neon-error" role="alert">{error}</p>}
      </section>
    </main>
  );
}
