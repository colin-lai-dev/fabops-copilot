import React, { useState } from "react";

// The injected source document with the malicious sentence marked, and a side-by-side view of
// the protected answer and the recorded control run without the permission pre-filter.

function Marked({ body }) {
  const handling = body.split("## 處理經過")[1]?.split("##")[0]?.trim() || "";
  const before = body.split("## 處理經過")[0];
  const title = before.match(/^# (.+)$/m)?.[1];
  return (
    <div className="source-doc">
      <div className="fine">{title}</div>
      <div className="fine">處理經過：</div>
      <p>
        <mark className="malicious">{handling}</mark>
      </p>
    </div>
  );
}

export default function Injection({ scene, run, cite }) {
  const [compare, setCompare] = useState(false);
  if (!scene?.injected) return null;
  const c = scene.control;
  return (
    <section className="panel injection" aria-label="注入對照">
      <div className="panel-head">
        <h2>檢索到的報告藏有注入文字</h2>
        {c && (
          <button type="button" aria-pressed={compare} onClick={() => setCompare(!compare)}>
            {compare ? "收起對照組" : "看對照組"}
          </button>
        )}
      </div>
      <p className="fine">
        測試用文件 <span className="code">{scene.injected.doc_id}</span>（只存在於隔離的測試資料庫，不在正式語料）。標示處是攻擊句：
      </p>
      <Marked body={scene.injected.body_md} />
      {compare && c && (
        <div className="compare">
          <div className="compare-col good">
            <div className="panel-sub">有防護（正式系統）</div>
            <p>{run.answer}</p>
            <p className="fine">引用：{run.citations?.length ? run.citations.map(cite) : "無"}</p>
          </div>
          <div className="compare-col bad">
            <div className="panel-sub">拿掉權限 pre-filter（eval 專用對照組，真實錄製）</div>
            <p>{c.answer}</p>
            <p className="fine">
              回答中用到此身分無權查看的文件：
              {c.hidden_in_answer.map((d) => (
                <span key={d} className="chip chip-bad code">{d}</span>
              ))}
            </p>
            <p className="fine">檢索結果中共有 {c.hidden_retrieved.length} 份越權文件。</p>
          </div>
        </div>
      )}
    </section>
  );
}
