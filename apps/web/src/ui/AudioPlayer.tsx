import { useEffect, useRef, useState } from "react";

const PlayIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
    <path d="M8 5v14l11-7z" />
  </svg>
);
const PauseIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
    <rect x="6" y="5" width="4" height="14" />
    <rect x="14" y="5" width="4" height="14" />
  </svg>
);

const fmtTime = (s: number) => {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
};

/** Reproductor de audio custom (sin los controles nativos del navegador). */
export function AudioPlayer({ src, autoPlay }: { src: string; autoPlay?: boolean }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onTime = () => setCurrent(el.currentTime);
    const onLoaded = () => {
      setDuration(el.duration || 0);
      if (autoPlay) el.play().catch(() => {});
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onLoaded);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onPause);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onLoaded);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onPause);
    };
  }, [autoPlay]);

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) el.play().catch(() => {});
    else el.pause();
  };

  const seek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const el = audioRef.current;
    if (!el) return;
    const v = Number(e.target.value);
    el.currentTime = v;
    setCurrent(v);
  };

  return (
    <div className="audio-player">
      <audio ref={audioRef} src={src} preload="metadata" />
      <button type="button" className="audio-play" onClick={toggle} aria-label={playing ? "Pausar" : "Reproducir"}>
        {playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <input
        type="range"
        className="audio-seek"
        min={0}
        max={duration || 0}
        step={0.1}
        value={current}
        onChange={seek}
        aria-label="Posición del audio"
      />
      <span className="audio-time">
        {fmtTime(current)} / {fmtTime(duration)}
      </span>
    </div>
  );
}
