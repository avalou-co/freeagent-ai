// Theme preference follows the Avalou website.
(() => {
  const root = document.documentElement;
  const selector = document.querySelector(".theme-selector");
  const options = [...selector.querySelectorAll("[data-theme-option]")];
  let preference = "system";
  try {
    const saved = localStorage.getItem("theme");
    if (["light", "system", "dark"].includes(saved)) preference = saved;
  } catch {
    /* System theme works without storage. */
  }
  const apply = () => {
    if (preference === "system") delete root.dataset.theme;
    else root.dataset.theme = preference;
    root.dataset.themePreference = preference;
    options.forEach((option) => {
      const active = option.dataset.themeOption === preference;
      option.setAttribute("aria-checked", String(active));
      option.tabIndex = active ? 0 : -1;
    });
  };
  const selectTheme = (option) => {
    preference = option.dataset.themeOption;
    apply();
    try {
      localStorage.setItem("theme", preference);
    } catch {
      /* A theme still lasts for this page. */
    }
  };
  options.forEach((option, index) => {
    option.addEventListener("click", () => selectTheme(option));
    option.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight" || event.key === "ArrowDown")
        next = (index + 1) % options.length;
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
        next = (index - 1 + options.length) % options.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = options.length - 1;
      else return;
      event.preventDefault();
      selectTheme(options[next]);
      options[next].focus();
    });
  });
  apply();
  selector.hidden = false;

  // Enhance linked examples into the line-tab pattern. Without JavaScript,
  // the links and all workflow content remain available.
  const list = document.querySelector(".workflow-shortcuts");
  const tabs = [...list.querySelectorAll("a")];
  const panels = tabs.map((tab) => document.getElementById(tab.hash.slice(1)));
  list.setAttribute("role", "tablist");
  tabs.forEach((tab, index) => {
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panels[index].id);
    panels[index].setAttribute("role", "tabpanel");
    panels[index].setAttribute("aria-labelledby", tab.id);
    panels[index].tabIndex = 0;
  });
  const select = (index, { focus = false, updateURL = false } = {}) => {
    tabs.forEach((tab, i) => {
      const active = i === index;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      tab.dataset.state = active ? "active" : "inactive";
      panels[i].hidden = !active;
    });
    if (focus) tabs[index].focus();
    if (updateURL && location.hash !== tabs[index].hash) {
      history.pushState(null, "", tabs[index].hash);
    }
  };
  const fromHash = () => tabs.findIndex((tab) => tab.hash === location.hash);
  select(Math.max(0, fromHash()));
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)
        return;
      event.preventDefault();
      select(index, { updateURL: true });
    });
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft")
        next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      select(next, { focus: true, updateURL: true });
    });
  });
  const restoreTab = () => {
    const index = fromHash();
    if (index >= 0) select(index);
  };
  addEventListener("hashchange", restoreTab);
  addEventListener("popstate", restoreTab);

  // Keep the instructions readable without JavaScript, then add disclosure controls.
  const steps = document.querySelector(".steps");
  const stepButtons = [];
  steps.querySelectorAll("li").forEach((step, index) => {
    const heading = step.querySelector("h3");
    const copy = step.querySelector("p");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "step-trigger";
    button.id = `step-trigger-${index}`;
    button.textContent = heading.textContent;
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", `step-detail-${index}`);
    heading.replaceChildren(button);
    const panel = document.createElement("div");
    panel.className = "step-detail";
    panel.id = `step-detail-${index}`;
    panel.setAttribute("role", "region");
    panel.setAttribute("aria-labelledby", button.id);
    panel.inert = true;
    panel.setAttribute("aria-hidden", "true");
    const inner = document.createElement("div");
    copy.replaceWith(panel);
    inner.append(copy);
    panel.append(inner);
    stepButtons.push({ button, panel });
    button.addEventListener("click", () => {
      const open = button.getAttribute("aria-expanded") !== "true";
      stepButtons.forEach((item) => {
        const expanded = item.button === button && open;
        item.button.setAttribute("aria-expanded", String(expanded));
        item.panel.setAttribute("aria-hidden", String(!expanded));
        item.panel.inert = !expanded;
        item.panel.classList.toggle("is-open", expanded);
      });
    });
  });
  steps.classList.add("steps-accordion");
})();
