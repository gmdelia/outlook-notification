function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function parseDate(iso) {
  try {
    return new Date(iso);
  } catch (e) {
    return null;
  }
}

function formatTime(date) {
  if (!date) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

async function openEventLink(url) {
  if (!url || !window.pywebview || !window.pywebview.api) return;
  try {
    await window.pywebview.api.open_event(url);
  } catch (err) {
    // ignore — link open failures are non-fatal in the UI
  }
}

function bindEventClicks(root) {
  root.querySelectorAll("[data-url]").forEach((el) => {
    el.addEventListener("click", () => {
      openEventLink(el.getAttribute("data-url"));
    });
  });
}

function render(payload) {
  document.getElementById("title").textContent = payload.title || "Eventi di oggi";
  document.getElementById("status").textContent = payload.status || "";

  const events = payload.events || [];
  const now = parseDate(payload.now) || new Date();
  const allDay = events.filter((e) => e.is_all_day);
  const timed = events
    .filter((e) => !e.is_all_day)
    .map((e) => ({
      ...e,
      startDate: parseDate(e.start),
      endDate: parseDate(e.end),
    }))
    .filter((e) => e.startDate)
    .sort((a, b) => a.startDate - b.startDate);

  const content = document.getElementById("content");
  let html = "";

  if (allDay.length) {
    html += '<div class="section-title">Tutto il giorno</div>';
    for (const e of allDay) {
      let text = e.subject || "(Senza titolo)";
      if (e.location) text += " · " + e.location;
      const clickable = e.web_link
        ? ` class="allday-item clickable" data-url="${escapeHtml(e.web_link)}" title="Apri in Outlook"`
        : ` class="allday-item"`;
      html += `<div${clickable}>• ${escapeHtml(text)}</div>`;
    }
  }

  if (!timed.length) {
    const msg = payload.synced_at
      ? "Nessun evento con orario per oggi."
      : "In attesa della sincronizzazione…";
    html += `<div class="empty">${escapeHtml(msg)}</div>`;
    content.innerHTML = html;
    bindEventClicks(content);
    return;
  }

  let nextIdx = -1;
  for (let i = 0; i < timed.length; i++) {
    if (timed[i].startDate >= now) {
      nextIdx = i;
      break;
    }
  }

  html += '<div class="timeline">';
  for (let i = 0; i < timed.length; i++) {
    const e = timed[i];
    const isNext = i === nextIdx;
    const isPast = e.startDate < now && !isNext;
    let cls = isNext ? "event-row next" : isPast ? "event-row past" : "event-row";
    if (e.web_link) cls += " clickable";

    if (isNext) {
      html += `<div class="now-marker"><span>Adesso ${escapeHtml(formatTime(now))}</span></div>`;
    }

    let timeStr = formatTime(e.startDate);
    if (e.endDate) timeStr += "–" + formatTime(e.endDate);
    let meta = e.location || "";
    if (isNext) meta = ("► prossimo  " + meta).trim();

    const dataUrl = e.web_link ? ` data-url="${escapeHtml(e.web_link)}" title="Apri in Outlook"` : "";
    html += `
      <div class="${cls}"${dataUrl}>
        <div class="time">${escapeHtml(timeStr)}</div>
        <div class="dot"></div>
        <div class="subject">${escapeHtml(e.subject || "(Senza titolo)")}</div>
        ${meta ? `<div class="meta">${escapeHtml(meta)}</div>` : ""}
      </div>`;
  }
  html += "</div>";
  content.innerHTML = html;
  bindEventClicks(content);
}

async function refresh() {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const payload = await window.pywebview.api.get_events();
    render(payload);
  } catch (err) {
    document.getElementById("status").textContent = "Errore caricamento eventi";
  }
}

window.addEventListener("pywebviewready", () => {
  refresh();
  setInterval(refresh, 3000);
});
