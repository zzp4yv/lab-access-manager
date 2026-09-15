(function () {
  // Se já autenticado, pula direto para o dashboard.
  if (Auth.getToken()) {
    window.location.href = "/dashboard.html";
    return;
  }

  const form = document.getElementById("login-form");
  const alertBox = document.getElementById("alert-box");
  const loginBtn = document.getElementById("login-btn");

  function showError(message) {
    alertBox.innerHTML = `<div class="alert alert-error">${message}</div>`;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    alertBox.innerHTML = "";
    loginBtn.disabled = true;
    loginBtn.textContent = "Entrando...";

    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    try {
      const result = await Api.login(email, password);
      Auth.setSession(result.access_token, result.admin);
      window.location.href = "/dashboard.html";
    } catch (err) {
      showError(err.message || "Não foi possível entrar. Verifique suas credenciais.");
    } finally {
      loginBtn.disabled = false;
      loginBtn.textContent = "Entrar";
    }
  });
})();
