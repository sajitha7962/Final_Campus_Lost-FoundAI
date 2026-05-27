/* ============================================================
   Lost & Found AI — Privacy-First Platform — script.js
   ============================================================ */

// ── Theme ─────────────────────────────────────────────────────────────────────
(function(){ document.documentElement.setAttribute("data-theme", localStorage.getItem("theme")||"dark"); })();
function toggleTheme(){ const n=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark"; document.documentElement.setAttribute("data-theme",n); localStorage.setItem("theme",n); }

// ── Utilities ─────────────────────────────────────────────────────────────────
const $  = id  => document.getElementById(id);
const qs = sel => document.querySelector(sel);

function setMsg(id, text, type="error"){
  const el=$(id); if(!el)return;
  el.innerText=text;
  el.style.color = type==="error"?"var(--red)": type==="ok"?"var(--green)":"var(--text2)";
}
function toIST(ts){
  if(!ts) return "—";
  // SQLite gives "YYYY-MM-DD HH:MM:SS" in UTC — replace space with T and add Z
  const utcStr = String(ts).trim().replace(" ","T") + (ts.includes("T") ? "" : "Z");
  const d = new Date(utcStr);
  if(isNaN(d)) return String(ts);
  // Format in IST (Asia/Kolkata = UTC+5:30)
  return d.toLocaleString("en-IN", {
    timeZone:    "Asia/Kolkata",
    day:         "2-digit",
    month:       "short",
    year:        "numeric",
    hour:        "2-digit",
    minute:      "2-digit",
    hour12:      true
  }) + " IST";
}
// Keep timeAgo as alias so all callers work
const timeAgo = toIST;
function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }
function skels(n){ return Array(n).fill(`<div class="skeleton sk-card"></div>`).join(""); }
function empty(icon,text){ return `<div class="empty-state"><div class="empty-icon">${icon}</div><div class="empty-text">${esc(text)}</div></div>`; }

async function api(url, opts={}){
  const res  = await fetch(url,{credentials:"include",...opts});
  const data = await res.json().catch(()=>({}));
  return {ok:res.ok, status:res.status, data};
}

// ── Auth ──────────────────────────────────────────────────────────────────────
async function login(){
  const u=($("username")||{}).value?.trim(), p=($("password")||{}).value?.trim();
  if(!u||!p){ setMsg("msg","Please fill all fields"); return; }
  setMsg("msg","Signing in…","info");
  const btn=$("loginBtn"); if(btn) btn.disabled=true;
  const {ok,data}=await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:u,password:p})});
  if(ok){ setMsg("msg","Welcome back! Redirecting…","ok"); setTimeout(()=>window.location.href="/dashboard",700); }
  else{ setMsg("msg",data.message||"Login failed"); if(btn){btn.disabled=false;btn.innerText="Sign In";} }
}

async function register(){
  const u=($("username")||{}).value?.trim(), p=($("password")||{}).value?.trim(), c=($("confirmPassword")||{}).value?.trim();
  if(!u||!p||!c){ setMsg("msg","Fill all fields"); return; }
  if(u.length<3){ setMsg("msg","Username ≥ 3 chars"); return; }
  if(p.length<4){ setMsg("msg","Password ≥ 4 chars"); return; }
  if(p!==c){ setMsg("msg","Passwords don't match"); return; }
  const btn=$("registerBtn"); if(btn) btn.disabled=true;
  setMsg("msg","Creating account…","info");
  const {ok,data}=await api("/api/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:u,password:p})});
  if(ok){ setMsg("msg","Account created! Redirecting…","ok"); setTimeout(()=>window.location.href="/login",900); }
  else{ setMsg("msg",data.message||"Registration failed"); if(btn){btn.disabled=false;btn.innerText="Create Account";} }
}

function logout(){ fetch("/api/logout",{credentials:"include"}).finally(()=>window.location.href="/login"); }

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard(){
  if(!$("stars"))return;
  const {ok,data}=await api("/api/user");
  if(!ok){ window.location.href="/login"; return; }

  if($("stars"))          $("stars").innerText         = data.stars;
  if($("credits"))        $("credits").innerText       = data.credits;
  if($("recoveries"))     $("recoveries").innerText    = data.recoveries;
  if($("userLevel"))      $("userLevel").innerText     = `${data.badge} ${data.level}`;
  if($("usernameDisplay"))$("usernameDisplay").innerText= data.username;

  const nb=$("notifBadge"); if(nb) nb.innerText=data.notifications>0?data.notifications:"";
  const mb=$("msgBadge");   if(mb) mb.innerText=data.unread_messages>0?data.unread_messages:"";

  loadMyReports();
  loadMyMatches();
  loadLeaderboard();
}

async function loadMyReports(){
  const box=$("myReports"); if(!box)return;
  box.innerHTML=skels(2);
  const {ok,data}=await api("/api/my_reports");
  if(!ok||!data.length){ box.innerHTML=empty("📋","No reports yet — click Report Item to start"); return; }
  box.innerHTML=data.map(r=>`
    <div class="report-row fade-in">
      ${r.image?`<img src="${esc(r.image)}" class="report-thumb" alt="">`:`<div class="report-thumb-ph">${r.type==="lost"?"😞":"📦"}</div>`}
      <div style="flex:1;min-width:0">
        <div class="report-title">${esc(r.item)}</div>
        <div class="report-desc">${esc(r.description||"")}</div>
        <div class="tags">
          <span class="tag tag-${r.type}">${r.type==="lost"?"🔴 Lost":"🟢 Found"}</span>
          <span class="tag ${r.status==="resolved"?"tag-resolved":"tag-active"}">${r.status}</span>
          <span class="tag">📍 ${esc(r.place||"—")}</span>
          <span class="tag">🕐 ${timeAgo(r.created_at)}</span>
        </div>
      </div>
      ${r.status!=="resolved"?`<button class="btn btn-sm btn-danger" onclick="deleteReport(${r.id},this)" style="flex-shrink:0;align-self:flex-start">🗑</button>`:""}
    </div>`).join("");
}

async function deleteReport(id,btn){
  if(!confirm("Delete this report?"))return;
  btn.disabled=true;
  const {ok}=await api(`/api/delete_report/${id}`,{method:"DELETE"});
  if(ok) loadMyReports(); else btn.disabled=false;
}

// ── Private Match Sessions ────────────────────────────────────────────────────
async function loadMyMatches(){
  const box=$("matchSessions"); if(!box)return;
  box.innerHTML=skels(2);
  const {ok,data}=await api("/api/my_matches");
  if(!ok||!data.length){
    box.innerHTML=empty("🔒","No matches yet. Submit a report and the AI will privately match you.");
    return;
  }
  box.innerHTML=data.map(s=>sessionCard(s)).join("");
}

function sessionCard(s){
  const statusLabel = s.status==="confirmed"
    ? `<span class="pill pill-green">✅ Confirmed</span>`
    : s.i_confirmed
      ? `<span class="pill pill-gold">⏳ Awaiting other party</span>`
      : `<span class="pill pill-purple">🔔 Action needed</span>`;

  const lockOrReveal = s.both_confirmed
    ? `<div class="reveal-banner">🔓 Recovery confirmed — full details revealed below</div>`
    : `<div class="lock-banner">🔒 Contact details & image hidden until both parties confirm recovery</div>`;

  const theirImg = s.both_confirmed && s.their_image
    ? `<img src="${esc(s.their_image)}" style="width:72px;height:72px;object-fit:cover;border-radius:8px;border:1px solid var(--border);margin-top:8px" alt="Item">`
    : "";

  const confirmBtn = (s.status!=="confirmed" && !s.i_confirmed)
    ? `<button class="btn btn-sm btn-success" onclick="confirmRecovery(${s.session_id},this)">✅ Confirm Recovery</button>`
    : "";

  const chatBtn = `<button class="btn btn-sm btn-cyan" onclick="window.location.href='/match/${s.session_id}'">💬 Private Chat</button>`;

  return `
  <div class="session-card ${s.status==="confirmed"?"confirmed":s.i_confirmed?"waiting":""} fade-in">
    <div class="session-header">
      <div>
        <div style="font-size:15px;font-weight:700">📦 ${esc(s.their_item)} <span style="font-size:12px;color:var(--text2)">matches your ${esc(s.my_item)}</span></div>
        <div class="tags" style="margin-top:6px">
          ${statusLabel}
          <span class="tag tag-${s.their_type}">${s.their_type==="lost"?"🔴 Lost":"🟢 Found"}</span>
          <span class="tag">🕐 ${timeAgo(s.created_at)}</span>
        </div>
      </div>
      <div class="session-score">${s.score}%</div>
    </div>
    <div class="score-bar"><div class="score-fill" style="width:${s.score}%"></div></div>
    ${lockOrReveal}
    <div class="session-meta">
      <span>📍 ${esc(s.their_place)}</span>
      <span>📅 ${esc(s.their_date)}</span>
      <span>📞 ${esc(s.their_contact)}</span>
    </div>
    ${theirImg}
    ${s.their_description && s.both_confirmed ? `<div style="font-size:13px;color:var(--text2);margin-top:8px">${esc(s.their_description)}</div>` : ""}
    <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
      ${confirmBtn}
      ${chatBtn}
    </div>
  </div>`;
}

async function confirmRecovery(sessionId, btn){
  if(!confirm("Confirm this item was actually recovered? This cannot be undone."))return;
  btn.disabled=true; btn.innerText="Confirming…";
  const {ok,data}=await api("/api/confirm_recovery",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:sessionId})
  });
  if(ok){
    if(data.status==="fully_confirmed"){
      showToast("🎉 Recovery confirmed! Full details are now revealed.","ok");
    } else {
      showToast("⏳ Your confirmation recorded. Waiting for the other party.","info");
    }
    loadMyMatches();
    loadDashboard();
  } else {
    showToast(data.message||"Error","error");
    btn.disabled=false; btn.innerText="✅ Confirm Recovery";
  }
}

// ── Match Detail / Private Chat Page ─────────────────────────────────────────
let _sessionId = null;
let _chatTimer  = null;
let _me         = null;

async function initMatchPage(sessionId){
  _sessionId = sessionId;
  const {ok,data} = await api("/api/user");
  if(!ok){ window.location.href="/login"; return; }
  _me = data.username;

  const msgBody = $("sessionMsgBody");
  if(msgBody) msgBody.dataset.me = _me;

  loadSessionDetails(sessionId);
  loadSessionMessages(sessionId);
  _chatTimer = setInterval(()=>loadSessionMessages(sessionId), 3000);
}

async function loadSessionDetails(sessionId){
  const {ok,data}=await api("/api/my_matches");
  if(!ok)return;
  const s = data.find(x=>x.session_id===sessionId);
  if(!s)return;

  const el=$("sessionDetails"); if(!el)return;
  const lockOrReveal = s.both_confirmed
    ? `<div class="reveal-banner">🔓 Full details revealed — recovery confirmed by both parties</div>`
    : `<div class="lock-banner">🔒 Contact & image hidden until both parties confirm</div>`;

  el.innerHTML=`
    <div class="detail-row">
      <div class="detail-box">
        <h4>Your ${esc(s.my_type)} report</h4>
        <div class="detail-field"><strong>Item</strong>${esc(s.my_item)}</div>
      </div>
      <div class="detail-box">
        <h4>Matched ${esc(s.their_type)} report</h4>
        <div class="detail-field"><strong>Item</strong>${esc(s.their_item)}</div>
        <div class="detail-field"><strong>Location</strong>${esc(s.their_place)}</div>
        <div class="detail-field"><strong>Date</strong>${esc(s.their_date)}</div>
        <div class="detail-field"><strong>Contact</strong>${esc(s.their_contact)}</div>
        <div class="detail-field"><strong>Description</strong>${esc(s.their_description)}</div>
        ${s.both_confirmed&&s.their_image?`<img src="${esc(s.their_image)}" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;margin-top:8px" alt="Item image">`:""}
      </div>
    </div>
    ${lockOrReveal}
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-top:4px">
      <div class="session-score">${s.score}% AI Confidence</div>
      ${s.status!=="confirmed"&&!s.i_confirmed?`<button class="btn btn-success" onclick="confirmRecovery(${s.session_id},this)">✅ Confirm Recovery</button>`:""}
      ${s.i_confirmed&&s.status!=="confirmed"?`<span class="pill pill-gold">⏳ Waiting for other party</span>`:""}
      ${s.status==="confirmed"?`<span class="pill pill-green">✅ Fully Confirmed</span>`:""}
    </div>`;
}

async function loadSessionMessages(sessionId){
  const box=$("sessionMsgBody"); if(!box)return;
  const atBottom = box.scrollTop+box.clientHeight >= box.scrollHeight-22;

  const {ok,data}=await api(`/api/session_messages/${sessionId}`);
  if(!ok)return;

  if(!data.length){
    box.innerHTML=`<div class="empty-state" style="padding:20px"><div class="empty-icon">💬</div><div>Start the conversation to verify your match</div></div>`;
    return;
  }
  box.innerHTML=data.map(m=>{
    const isMe=(m.sender===_me);
    return `<div class="cp-msg ${isMe?"me":"them"}">
      <div class="cp-bubble">${esc(m.body)}</div>
      <div class="cp-ts">${isMe?"You":"Them"} · ${timeAgo(m.created_at)}</div>
    </div>`;
  }).join("");
  if(atBottom) box.scrollTop=box.scrollHeight;
}

async function sendSessionMessage(){
  const input=$("sessionMsgInput");
  const body=input?.value?.trim();
  if(!body||!_sessionId)return;
  input.value="";
  await api("/api/send_session_message",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({session_id:_sessionId,body})
  });
  loadSessionMessages(_sessionId);
}

// ── Leaderboard ───────────────────────────────────────────────────────────────
async function loadLeaderboard(){
  const box=$("leaderboard"); if(!box)return;
  const {ok,data}=await api("/api/leaderboard");
  if(!ok||!data.length){ box.innerHTML=empty("🏆","No rankings yet"); return; }
  const medals=["🥇","🥈","🥉"];
  box.innerHTML=data.map((u,i)=>`
    <div class="leader-row">
      <div class="leader-rank">${medals[i]||(i+1)}</div>
      <div class="leader-badge">${esc(u.badge)}</div>
      <div class="leader-name">${esc(u.username)}<br><small class="text-muted">${esc(u.level)} · ${u.recoveries} recoveries</small></div>
      <div class="leader-stats">⭐ ${u.stars}<br>💎 ${u.credits}</div>
    </div>`).join("");
}

// ── Report Form ───────────────────────────────────────────────────────────────
async function submitReport(){
  const btn=$("submitBtn");
  const fields=["type","item","description","place","date","contact"];
  for(const f of fields){
    if(!$(f)?.value?.trim()){ setMsg("reportMsg",`Field '${f}' is required`); return; }
  }
  if(btn){ btn.disabled=true; btn.innerText="Submitting…"; }
  setMsg("reportMsg","Uploading…","info");

  const fd=new FormData();
  fields.forEach(f=>fd.append(f,$(f).value.trim()));
  const imgFile=$("image")?.files?.[0]; if(imgFile) fd.append("image",imgFile);
  const capData=$("capturedData")?.value;
  if(capData&&capData.startsWith("data:image")){
    const blob=await(await fetch(capData)).blob();
    fd.append("image",blob,"capture.jpg");
  }

  const {ok,data}=await api("/api/report",{method:"POST",body:fd});
  if(ok){
    setMsg("reportMsg","Reported! AI is now scanning for private matches…","ok");
    setTimeout(()=>window.location.href="/dashboard",1200);
  } else {
    setMsg("reportMsg",data.message||"Submission failed");
    if(btn){ btn.disabled=false; btn.innerText="Submit Report"; }
  }
}

// ── Camera ────────────────────────────────────────────────────────────────────
let _stream=null;
async function openCamera(){
  const video=$("cameraStream"),btn=$("cameraBtn"); if(!video)return;
  try{
    _stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}});
    video.srcObject=_stream; video.style.display="block"; video.play();
    if(btn){ btn.innerHTML="📸 Capture Photo"; btn.setAttribute("onclick","capturePhoto()"); }
  } catch(e){ alert("Camera access denied or unavailable."); }
}
function capturePhoto(){
  const video=$("cameraStream"),prev=$("imgPreview"),hidden=$("capturedData"); if(!video)return;
  const c=document.createElement("canvas"); c.width=video.videoWidth; c.height=video.videoHeight;
  c.getContext("2d").drawImage(video,0,0);
  const url=c.toDataURL("image/jpeg",.85);
  if(prev){ prev.src=url; prev.style.display="block"; }
  if(hidden) hidden.value=url;
  if(_stream){ _stream.getTracks().forEach(t=>t.stop()); _stream=null; }
  video.style.display="none";
  const btn=$("cameraBtn");
  if(btn){ btn.innerHTML="📷 Open Camera"; btn.setAttribute("onclick","openCamera()"); }
}
function previewImage(e){
  const f=e.target.files[0],p=$("imgPreview");
  if(f&&p){ p.src=URL.createObjectURL(f); p.style.display="block"; }
}

// ── Floating AI Chatbot ───────────────────────────────────────────────────────
let chatOpen=false;
function toggleChat(){
  chatOpen=!chatOpen;
  const w=qs(".chat-window"); if(w) w.classList.toggle("open",chatOpen);
  if(chatOpen){ loadBotHistory(); setTimeout(()=>qs(".chat-input-row input")?.focus(),300); }
}
async function loadBotHistory(){
  const box=$("chatMessages"); if(!box)return;
  const {ok,data}=await api("/api/chat_history");
  if(!ok||!data.length){ box.innerHTML=botBubble("Hey! 👋 I'm your private AI assistant. How can I help?"); return; }
  box.innerHTML=data.map(m=>m.role==="user"?userBubble(m.message):botBubble(m.message)).join("");
  box.scrollTop=box.scrollHeight;
}
function botBubble(t){
  return `<div class="chat-msg bot"><div class="chat-bubble">${esc(t).replace(/\n/g,"<br>").replace(/\*\*(.*?)\*\*/g,"<b>$1</b>")}</div><div class="chat-time">AI Assistant</div></div>`;
}
function userBubble(t){
  return `<div class="chat-msg user"><div class="chat-bubble">${esc(t)}</div></div>`;
}
async function sendChat(){
  const inp=qs(".chat-input-row input"),msg=inp?.value?.trim();
  if(!msg)return; inp.value="";
  const box=$("chatMessages"); if(!box)return;
  box.innerHTML+=userBubble(msg);
  const tid="typing_"+Date.now();
  box.innerHTML+=`<div class="chat-msg bot" id="${tid}"><div class="chat-bubble"><div class="chat-typing"><span></span><span></span><span></span></div></div></div>`;
  box.scrollTop=box.scrollHeight;
  const {ok,data}=await api("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg})});
  const el=$(tid); if(el)el.remove();
  box.innerHTML+=botBubble(ok?data.response:"Sorry, something went wrong.");
  box.scrollTop=box.scrollHeight;
}

// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(msg,type="info"){
  const t=document.createElement("div");
  t.className="fade-in";
  t.style.cssText=`position:fixed;top:80px;right:20px;z-index:9999;padding:12px 18px;border-radius:10px;font-size:13px;font-weight:600;max-width:300px;box-shadow:0 4px 20px rgba(0,0,0,.3);background:${type==="ok"?"var(--green)":type==="error"?"var(--red)":"var(--accent2)"};color:#fff`;
  t.innerText=msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(),3500);
}

// ── Notifications panel ───────────────────────────────────────────────────────
async function loadNotifications(){
  const box=$("notifList"); if(!box)return;
  const {ok,data}=await api("/api/notifications");
  if(!ok)return;
  box.innerHTML=data.length
    ? data.map(n=>`<div class="report-row"><div style="flex:1"><div class="report-title">${esc(n.text)}</div><div class="text-xs text-muted">${timeAgo(n.created_at)}</div></div></div>`).join("")
    : empty("🔔","No notifications");
}

// ── Admin ─────────────────────────────────────────────────────────────────────
async function loadAdminStats(){
  const {ok,data}=await api("/api/admin/stats"); if(!ok)return;
  const map={"aTotal":data.total_users,"aReports":data.total_reports,"aActive":data.active_reports,
    "aResolved":data.resolved,"aSessions":data.match_sessions,"aConfirmed":data.confirmed_matches,"aMsgs":data.messages};
  for(const [id,val] of Object.entries(map)){ const el=$(id);if(el)el.innerText=val; }
}
async function loadAdminUsers(){
  const box=$("adminUsers"); if(!box)return;
  const {ok,data}=await api("/api/admin/users"); if(!ok)return;
  box.innerHTML=data.map(u=>`<tr>
    <td>${u.id}</td><td><b>${esc(u.username)}</b></td>
    <td><span class="pill ${u.role==="admin"?"pill-purple":"pill-cyan"}">${u.role}</span></td>
    <td>${esc(u.badge)} ${esc(u.level)}</td>
    <td>⭐${u.stars} 💎${u.credits} 🔁${u.recoveries}</td>
    <td><span class="pill ${u.banned?"pill-red":"pill-green"}">${u.banned?"Banned":"Active"}</span></td>
    <td style="display:flex;gap:5px">
      ${u.banned
        ?`<button class="btn btn-sm btn-success" onclick="adminAct('unban','${esc(u.username)}')">Unban</button>`
        :`<button class="btn btn-sm btn-danger"  onclick="adminAct('ban','${esc(u.username)}')">Ban</button>`}
      <button class="btn btn-sm btn-ghost" onclick="adminAct('make_admin','${esc(u.username)}')">Admin</button>
    </td></tr>`).join("");
}
async function loadAdminReports(){
  const box=$("adminReports"); if(!box)return;
  const {ok,data}=await api("/api/admin/reports"); if(!ok)return;
  box.innerHTML=data.map(r=>`<tr>
    <td>${r.id}</td><td>${esc(r.username)}</td>
    <td><span class="tag tag-${r.type}">${r.type}</span></td>
    <td>${esc(r.item)}</td><td>${esc(r.place||"—")}</td>
    <td><span class="pill ${r.status==="active"?"pill-green":"pill-cyan"}">${r.status}</span></td>
    <td><button class="btn btn-sm btn-danger" onclick="adminDelReport(${r.id},this)">Delete</button></td>
  </tr>`).join("");
}
async function loadAdminSessions(){
  const box=$("adminSessions"); if(!box)return;
  const {ok,data}=await api("/api/admin/sessions"); if(!ok)return;
  box.innerHTML=data.map(s=>`<tr>
    <td>${s.id}</td><td>${esc(s.user_lost)}</td><td>${esc(s.user_found)}</td>
    <td>${Math.round(s.score*100)}%</td>
    <td><span class="pill ${s.status==="confirmed"?"pill-green":"pill-gold"}">${s.status}</span></td>
    <td>${timeAgo(s.created_at)}</td>
  </tr>`).join("");
}
async function loadAdminActivity(){
  const box=$("adminActivity"); if(!box)return;
  const {ok,data}=await api("/api/admin/activity"); if(!ok)return;
  box.innerHTML=data.map(a=>`<tr><td>${esc(a.username||"—")}</td><td>${esc(a.action)}</td><td>${esc(a.detail||"")}</td><td>${timeAgo(a.created_at)}</td></tr>`).join("");
}
async function adminAct(action,username){
  if(!confirm(`${action} ${username}?`))return;
  const {ok}=await api(`/api/admin/${action}/${encodeURIComponent(username)}`,{method:"POST"});
  if(ok) loadAdminUsers();
}
async function adminDelReport(id,btn){
  if(!confirm("Delete?"))return; btn.disabled=true;
  const {ok}=await api(`/api/admin/delete_report/${id}`,{method:"DELETE"});
  if(ok) btn.closest("tr").remove(); else btn.disabled=false;
}
function switchAdminTab(tab){
  document.querySelectorAll(".admin-panel").forEach(p=>p.style.display="none");
  document.querySelectorAll(".admin-nav-item").forEach(n=>n.classList.remove("active"));
  const panel=$(tab); if(panel) panel.style.display="block";
  event.currentTarget.classList.add("active");
  if(tab==="panelUsers")    loadAdminUsers();
  if(tab==="panelReports")  loadAdminReports();
  if(tab==="panelSessions") loadAdminSessions();
  if(tab==="panelActivity") loadAdminActivity();
}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded",()=>{
  document.addEventListener("keydown",e=>{
    if(e.key!=="Enter")return;
    if($("loginBtn"))    login();
    if($("registerBtn")) register();
    if(qs(".chat-input-row input")===document.activeElement) sendChat();
    if($("sessionMsgInput")===document.activeElement) sendSessionMessage();
  });

  loadDashboard();

  if($("panelStats")){ loadAdminStats(); $("panelStats").style.display="block"; }
});
