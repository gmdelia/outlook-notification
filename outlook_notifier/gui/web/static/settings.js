function setMessage(text, kind) {
  const el = document.getElementById("message");
  el.textContent = text || "";
  el.className = "message" + (kind ? " " + kind : "");
}

function fillForm(config) {
  document.getElementById("poll_interval_minutes").value = config.poll_interval_minutes ?? 5;
  document.getElementById("reminder_minutes").value = config.reminder_minutes ?? "15, 5";
  document.getElementById("notifications_enabled").checked = !!config.notifications_enabled;
  document.getElementById("sound_enabled").checked = !!config.sound_enabled;
  document.getElementById("sound_file").value = config.sound_file || "";
  document.getElementById("notify_all_day_events").checked = !!config.notify_all_day_events;
  document.getElementById("all_day_reminder_time").value = config.all_day_reminder_time || "09:00";
  document.getElementById("timezone").value = config.timezone || "";
  document.getElementById("outlook_url").value = config.outlook_url || "";
}

function collectForm() {
  return {
    poll_interval_minutes: document.getElementById("poll_interval_minutes").value,
    reminder_minutes: document.getElementById("reminder_minutes").value,
    notifications_enabled: document.getElementById("notifications_enabled").checked,
    sound_enabled: document.getElementById("sound_enabled").checked,
    sound_file: document.getElementById("sound_file").value,
    notify_all_day_events: document.getElementById("notify_all_day_events").checked,
    all_day_reminder_time: document.getElementById("all_day_reminder_time").value,
    timezone: document.getElementById("timezone").value,
    outlook_url: document.getElementById("outlook_url").value,
  };
}

async function loadConfig() {
  const config = await window.pywebview.api.get_config();
  fillForm(config);
}

document.getElementById("settings-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  setMessage("Salvataggio…");
  const result = await window.pywebview.api.save_config(collectForm());
  if (result.ok) {
    fillForm(result.config);
    setMessage(result.message, "ok");
  } else {
    setMessage(result.message, "error");
  }
});

document.getElementById("browse-sound").addEventListener("click", async () => {
  const result = await window.pywebview.api.browse_sound_file();
  if (result.ok && result.path) {
    document.getElementById("sound_file").value = result.path;
  }
});

document.getElementById("reconnect").addEventListener("click", async () => {
  const result = await window.pywebview.api.request_reconnect();
  setMessage(result.message, "ok");
});

document.getElementById("close").addEventListener("click", async () => {
  await window.pywebview.api.close_window();
});

window.addEventListener("pywebviewready", () => {
  loadConfig().catch(() => setMessage("Errore caricamento impostazioni", "error"));
});
