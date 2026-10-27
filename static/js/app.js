(function () {
  "use strict";

  // 1) Ask for confirmation on forms that opt in with data-confirm.
  //    If data-confirm-value is set, only ask when the select has that value.
  //    This listener is registered first so a cancelled form is never locked.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var expected = form.getAttribute("data-confirm-value");
      var select = form.querySelector("select");
      var needsConfirmation = !expected || (select && select.value === expected);
      if (needsConfirmation && !window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  // 2) Prevent double submits: disable submit buttons once a form is sent.
  document.querySelectorAll("form[method='post']").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (event.defaultPrevented) {
        return;
      }
      var buttons = form.querySelectorAll("button[type='submit']");
      window.setTimeout(function () {
        buttons.forEach(function (button) {
          button.disabled = true;
        });
      }, 0);
    });
  });

  // Coming back with the browser's back button must not leave buttons disabled.
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
      document.querySelectorAll("button[type='submit']").forEach(function (button) {
        button.disabled = false;
      });
    }
  });

  // 3) Make flash messages dismissible, and fade success messages away.
  document.querySelectorAll(".messages .alert").forEach(function (alert) {
    var close = document.createElement("button");
    close.type = "button";
    close.className = "alert-close";
    close.setAttribute("aria-label", "Dismiss message");
    close.textContent = "\u00d7";
    close.addEventListener("click", function () {
      alert.remove();
    });
    alert.appendChild(close);

    if (alert.classList.contains("alert-success")) {
      window.setTimeout(function () {
        alert.remove();
      }, 6000);
    }
  });
})();