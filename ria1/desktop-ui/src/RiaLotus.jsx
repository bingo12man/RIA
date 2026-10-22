import { useState } from "react";
import "./RiaLotus.css";

const EXPRESSIONS = ["idle", "happy", "listening", "speaking", "thinking", "sleepy", "wink", "alert"];

function chooseExpression({ mood, recording, processing, quiet, reminder }) {
  if (quiet || mood === "sleepy") return "sleepy";
  if (recording || mood === "listening") return "listening";
  if (mood === "speaking") return "speaking";
  if (reminder) return "alert";
  if (processing || mood === "thinking" || mood === "curious") return "thinking";
  if (mood === "happy") return "happy";
  if (mood === "wink") return "wink";
  if (mood === "alert") return "alert";
  return "idle";
}

/** Purely visual. Keeps the existing .ria-face / .mouth hooks for production lip sync. */
export default function RiaLotus(props) {
  const [preview, setPreview] = useState(null);
  const state = preview || chooseExpression(props);
  return (
    <div className="ria-lotus-container">
      <div className={`ria-lotus ria-lotus--${state}`} role="img" aria-label={`RIA is ${state}`}>
        <div className="ria-lotus-halo" aria-hidden="true" />
        <svg className="ria-lotus-petals" viewBox="0 0 500 500" aria-hidden="true" focusable="false">
          <defs>
            <linearGradient id="ria-petal-back" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#14d9ff" stopOpacity=".95" />
              <stop offset=".45" stopColor="#4455df" stopOpacity=".93" />
              <stop offset="1" stopColor="#f875dc" stopOpacity=".94" />
            </linearGradient>
            <linearGradient id="ria-petal-front" x1="0" y1="1" x2=".8" y2="0">
              <stop offset="0" stopColor="#28caff" stopOpacity=".94" />
              <stop offset=".5" stopColor="#5844c7" stopOpacity=".94" />
              <stop offset="1" stopColor="#e36eff" stopOpacity=".88" />
            </linearGradient>
            <linearGradient id="ria-petal-rim" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#7dfcff" />
              <stop offset=".5" stopColor="#8882ff" />
              <stop offset="1" stopColor="#ffb3e8" />
            </linearGradient>
            <filter id="ria-lotus-glow" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="7" />
            </filter>
          </defs>
          <ellipse className="ria-lotus-ground" cx="250" cy="445" rx="177" ry="22" fill="#7154ff" opacity=".24" filter="url(#ria-lotus-glow)" />
          <g className="ria-petal ria-petal--back-left">
            <path d="M242 392 C76 393 36 250 95 160 C130 110 197 147 242 217 C271 261 279 324 242 392Z" fill="url(#ria-petal-back)" stroke="url(#ria-petal-rim)" strokeWidth="5" />
          </g>
          <g className="ria-petal ria-petal--back-center">
            <path d="M248 392 C115 346 102 147 247 84 C392 147 380 349 248 392Z" fill="url(#ria-petal-back)" stroke="url(#ria-petal-rim)" strokeWidth="5" />
          </g>
          <g className="ria-petal ria-petal--back-right">
            <path d="M256 392 C423 393 466 250 405 160 C370 109 305 147 256 217 C226 261 222 325 256 392Z" fill="url(#ria-petal-back)" stroke="url(#ria-petal-rim)" strokeWidth="5" />
          </g>
          <g className="ria-petal ria-petal--side-left">
            <path d="M257 424 C121 432 58 337 67 252 C76 201 115 208 171 253 C204 278 257 348 257 424Z" fill="url(#ria-petal-front)" stroke="url(#ria-petal-rim)" strokeWidth="5" />
          </g>
          <g className="ria-petal ria-petal--side-right">
            <path d="M243 424 C379 432 442 337 433 252 C424 201 385 208 329 253 C296 278 243 348 243 424Z" fill="url(#ria-petal-front)" stroke="url(#ria-petal-rim)" strokeWidth="5" />
          </g>
        </svg>
        <div className={`ria-face ria-lotus-face ${props.mood || "idle"}`} aria-hidden="true">
          <div className="ria-lotus-eyes eyes"><span className="eye" /><span className="eye" /></div>
          <span className="mouth" /><span className="cheek cheek-left" /><span className="cheek cheek-right" />
        </div>
        <svg className="ria-lotus-front" viewBox="0 0 500 500" aria-hidden="true" focusable="false">
          <g className="ria-petal ria-petal--front-left">
            <path d="M249 428 C146 449 65 399 64 305 C112 283 189 315 261 374Z" fill="url(#ria-lotus-front-fill)" stroke="#7ce8ff" strokeWidth="5" />
          </g>
          <g className="ria-petal ria-petal--front-right">
            <path d="M250 428 C353 449 435 399 436 305 C388 283 311 315 239 374Z" fill="url(#ria-lotus-front-fill)" stroke="#df9aff" strokeWidth="5" />
          </g>
          <defs><linearGradient id="ria-lotus-front-fill" x1="0" x2="1" y1=".2" y2="1"><stop stopColor="#21d9ff" stopOpacity=".94"/><stop offset=".50" stopColor="#4342b5" stopOpacity=".96"/><stop offset="1" stopColor="#b65cf8" stopOpacity=".92"/></linearGradient></defs>
        </svg>
        <div className="ria-lotus-particle ria-lotus-particle--a" />
        <div className="ria-lotus-particle ria-lotus-particle--b" />
        <div className="ria-lotus-particle ria-lotus-particle--c" />
        <div className="ria-lotus-bubble" aria-hidden="true">{state === "sleepy" ? "zZ" : state === "thinking" ? "···" : state === "alert" ? "!" : ""}</div>
      </div>
      <details className="ria-lotus-preview">
        <summary>Preview expressions</summary>
        <div className="ria-lotus-preview-options" role="group" aria-label="Preview RIA avatar expressions">
          {EXPRESSIONS.map(expression => (
            <button type="button" key={expression} className={state === expression ? "active" : ""}
              aria-pressed={preview === expression} onClick={() => setPreview(expression)}>
              {expression}
            </button>
          ))}
          <button type="button" onClick={() => setPreview(null)}>Live</button>
        </div>
      </details>
    </div>
  );
}
