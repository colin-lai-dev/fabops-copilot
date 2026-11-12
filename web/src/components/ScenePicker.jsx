import React, { useEffect, useId, useRef, useState } from "react";
import { useT } from "../i18n.js";

// Recorded-question picker for the replay (replaces a native <select>, handoff 017 #2).
// A button opens an ARIA listbox grouped by mode; each option shows the full question (up to two
// lines). No extra tags (handoff 019: noise).
// Keyboard: Enter / Space / arrows open; arrows, Home, End move; Enter selects; Esc / Tab close.

const MODES = ["rag", "fixed", "agent"];

export default function ScenePicker({ scenes, value, onChange }) {
  const t = useT();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrap = useRef(null);
  const button = useRef(null);
  const list = useRef(null);
  const groups = MODES.map((m) => [m, scenes.filter((s) => s.mode === m)]).filter(([, g]) => g.length);
  const flat = groups.flatMap(([, g]) => g);
  const selected = flat.find((s) => s.id === value);
  const optId = (s) => `${id}-${s.id}`;

  useEffect(() => {
    if (!open) return undefined;
    setActive(Math.max(0, flat.findIndex((s) => s.id === value)));
    list.current?.focus();
    const away = (e) => !wrap.current?.contains(e.target) && setOpen(false);
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  useEffect(() => {
    if (open) document.getElementById(optId(flat[active] || {}))?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(s) {
    onChange(s.id);
    setOpen(false);
    button.current?.focus();
  }

  function onButtonKey(e) {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      setOpen(true);
    }
  }

  function onListKey(e) {
    const last = flat.length - 1;
    const moves = { ArrowDown: Math.min(last, active + 1), ArrowUp: Math.max(0, active - 1), Home: 0, End: last };
    if (e.key in moves) {
      e.preventDefault();
      setActive(moves[e.key]);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (flat[active]) choose(flat[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  }

  if (!flat.length) return <p className="fine pick-empty">{t("ask.none")}</p>;
  return (
    <div className="pick" ref={wrap}>
      <button
        type="button"
        ref={button}
        className="pick-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-label={`${t("ask.recorded")}: ${selected?.question || ""}`}
        onClick={() => setOpen(!open)}
        onKeyDown={onButtonKey}
      >
        <span className="pick-text">
          <span className="pick-q">{selected?.question || t("ask.recorded")}</span>
          {selected && (
            <span className="pick-meta">
              <span className="pick-mode">{t(`mode.${selected.mode}`)}</span>
            </span>
          )}
        </span>
        <span className="pick-chevron" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <div
          id={`${id}-list`}
          ref={list}
          role="listbox"
          tabIndex={-1}
          className="pick-list"
          aria-label={t("ask.recorded")}
          aria-activedescendant={flat[active] ? optId(flat[active]) : undefined}
          onKeyDown={onListKey}
        >
          {groups.map(([m, g]) => (
            <div key={m} role="group" aria-labelledby={`${id}-g-${m}`}>
              <div id={`${id}-g-${m}`} className="pick-group" role="presentation">
                {t(`mode.${m}`)}
              </div>
              {g.map((s) => {
                const i = flat.indexOf(s);
                return (
                  <div
                    key={s.id}
                    id={optId(s)}
                    role="option"
                    aria-selected={s.id === value}
                    className={`pick-opt ${i === active ? "pick-active" : ""} ${s.id === value ? "pick-chosen" : ""}`}
                    onPointerEnter={() => setActive(i)}
                    onClick={() => choose(s)}
                  >
                    <span className="pick-q">{s.question}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
