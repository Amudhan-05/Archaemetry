// Theme switch: light/dark, defaults to the system setting, remembered per browser.
(function () {
  var root = document.documentElement;
  var btn = document.getElementById("theme");
  function current() {
    return root.dataset.theme ||
      (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  function paint() {
    if (!btn) return;
    var t = current();
    btn.textContent = t === "dark" ? "☀ Light mode" : "☾ Dark mode";
    btn.setAttribute("aria-label", "Switch to " + (t === "dark" ? "light" : "dark") + " mode");
  }
  if (btn) btn.addEventListener("click", function () {
    var next = current() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) {}
    paint();
  });
  paint();
})();
