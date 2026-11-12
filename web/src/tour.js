// The guided steps. Each step is a recorded question (`q`, a six-identity group id) seen as one
// identity (`as`); `question` / `mode` pre-fill the live backend. `*_en` is the English
// interface text; recorded answers stay in Chinese.

const EPD_Q = "FX1 蝕刻機台發生終點偵測逾時（ETC-EPD-0118），量測超出上限後要等幾分鐘重測？要通知誰？";
const TRIAGE_Q = "FX2-POLISHER-03-CHC 剛發生 CMP-SLR-0822（研磨液流量不足），請先確認腔體狀態，再依 SOP 處理。";

export const TOUR = [
  {
    key: "sop",
    title: "問 SOP",
    title_en: "Ask an SOP",
    q: "epd",
    as: "eng_fx1_etch",
    mode: "rag",
    question: EPD_Q,
    explain: "工程師問 SOP，回答只引用他看得到的現行版。上面六片晶圓，是六個身分各自看得到的文件。",
    explain_en:
      "An engineer asks about an SOP; the answer cites only the current version he may see. The six wafers are what each of six identities may see.",
    caption_en: "Cited answer from the current SOP version; six wafers show what six identities may see.",
  },
  {
    key: "permission",
    title: "權限擋下",
    title_en: "Permission block",
    q: "epd",
    as: "op_fx1_etch",
    mode: "rag",
    question: EPD_Q,
    explain: "同一題換成作業員。他只看得到 1 份文件，那份 SOP 在檢索之前就被濾掉，所以答不出來。",
    explain_en:
      "The same question as an operator. He may see 1 document; the SOP is filtered out before retrieval, so there is no answer.",
    caption_en: "Same question as an operator: 1 of 192 documents is visible, filtering happens before retrieval.",
  },
  {
    key: "six",
    title: "六身分並排",
    title_en: "Six identities",
    q: "epd",
    as: "eng_fx1_etch",
    compare: true,
    mode: "rag",
    question: EPD_Q,
    explain:
      "同一題，六個身分各問一次。三個身分看不到那份 SOP；看得到的三個裡，系統管理員的檢索沒拿到關鍵段落。",
    explain_en:
      "One question, asked once by each identity. Three cannot see the SOP; of the three who can, the administrator's retrieval missed the key section.",
    caption_en: "The same question as all six identities: the only difference is permission.",
  },
  {
    key: "agent",
    title: "Agent 逐步查詢",
    title_en: "Agent steps",
    q: "triage",
    as: "mgr_fx2_all",
    mode: "agent",
    question: TRIAGE_Q,
    explain: "廠務經理請 agent 處理 alarm。它用唯讀工具一步一步查，最後只能提出建議，不能自己執行。",
    explain_en:
      "A fab manager asks the agent to handle an alarm. It looks things up with read-only tools, step by step, and can only propose an action.",
    caption_en: "The agent calls read-only tools step by step, then can only propose an action.",
  },
  {
    key: "approval",
    title: "人工核准",
    title_en: "Human approval",
    q: "triage",
    as: "mgr_fx2_all",
    approval: true,
    mode: "agent",
    question: TRIAGE_Q,
    explain: "建議要有人核准。提出者自己不行，看不到目標的人不行，有權限的人才行；每一次嘗試都寫進 audit log。",
    explain_en:
      "A proposal needs a person. Not its requester, not someone who cannot see the target; only a qualified approver. Every attempt goes to the audit log.",
    caption_en: "The requester cannot approve; a qualified approver executes it, and every step is audited.",
  },
  {
    key: "injection",
    title: "擋下注入",
    title_en: "Injection blocked",
    q: "injection",
    as: "eng_fx1_etch",
    mode: "rag",
    question: "FX1-ETCHER-02 這次壓力異常要怎麼處理？",
    explain: "檢索到的報告裡藏了一句指令。系統把文件當成資料，不照做；下方可以對照拿掉權限過濾的結果。",
    explain_en:
      "A retrieved report hides an instruction. Documents are data, so it is not followed; the control below shows what happens without the permission filter.",
    caption_en: "A retrieved report hides an instruction; it is treated as data. The control without the pre-filter leaks restricted reports.",
  },
  {
    key: "results",
    title: "結果",
    title_en: "Results",
    results: true,
    explain: "每個數字都在凍結的 test 上只跑一次，附樣本數與 baseline。",
    explain_en: "Every number comes from a frozen test set, run once, with n and a baseline.",
    caption_en: "Frozen test sets, run once, with n and baselines; no claim that the agent beats the fixed workflow.",
  },
];
