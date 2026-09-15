(function () {
  const adminsTable = document.getElementById("admins-table");
  const newAdminForm = document.getElementById("new-admin-form");
  const newAdminAlert = document.getElementById("new-admin-alert");
  const submitAdminBtn = document.getElementById("submit-admin-btn");

  async function loadAdmins() {
    try {
      const admins = await Api.listAdmins();
      renderAdminsTable(admins);
    } catch (err) {
      adminsTable.innerHTML = `<div class="alert alert-error">${err.message || "Falha ao carregar administradores."}</div>`;
    }
  }

  function renderAdminsTable(admins) {
    if (admins.length === 0) {
      adminsTable.innerHTML = `<p class="empty-state">Nenhum administrador cadastrado.</p>`;
      return;
    }
    const currentAdmin = Auth.getAdmin();

    adminsTable.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Nome</th><th>Email</th><th>Status</th><th>Último login</th><th>Ações</th></tr></thead>
        <tbody>
          ${admins
            .map(
              (a) => `
            <tr>
              <td data-label="Nome">${a.full_name}</td>
              <td data-label="Email">${a.email}</td>
              <td data-label="Status">${a.is_active ? '<span class="badge badge-active">Ativo</span>' : '<span class="badge badge-revoked">Inativo</span>'}</td>
              <td data-label="Último login">${formatDateTime(a.last_login_at)}</td>
              <td data-label="Ações">
                ${
                  currentAdmin && a.id !== currentAdmin.id
                    ? `<button class="btn btn-secondary btn-sm" data-action="toggle" data-id="${a.id}" data-active="${a.is_active}">${a.is_active ? "Desativar" : "Reativar"}</button>`
                    : '<span class="helper-text">Você</span>'
                }
              </td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;

    adminsTable.querySelectorAll("[data-action='toggle']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          const isActive = btn.dataset.active === "true";
          await Api.updateAdmin(btn.dataset.id, { is_active: !isActive });
          await loadAdmins();
        } catch (err) {
          window.alert(err.message || "Falha ao atualizar administrador.");
          btn.disabled = false;
        }
      });
    });
  }

  newAdminForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    newAdminAlert.innerHTML = "";
    submitAdminBtn.disabled = true;
    submitAdminBtn.textContent = "Salvando...";

    try {
      await Api.createAdmin({
        full_name: document.getElementById("admin_full_name").value.trim(),
        email: document.getElementById("admin_email").value.trim(),
        password: document.getElementById("admin_password").value,
      });
      newAdminAlert.innerHTML = `<div class="alert alert-success">Administrador cadastrado com sucesso.</div>`;
      newAdminForm.reset();
      await loadAdmins();
    } catch (err) {
      newAdminAlert.innerHTML = `<div class="alert alert-error">${err.message || "Falha ao cadastrar administrador."}</div>`;
    } finally {
      submitAdminBtn.disabled = false;
      submitAdminBtn.textContent = "Adicionar administrador";
    }
  });

  loadAdmins();
})();
