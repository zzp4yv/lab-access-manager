(function () {
  renderTopbar("users");

  const alertBox = document.getElementById("alert-box");
  const usersTable = document.getElementById("users-table");
  const statusFilter = document.getElementById("status-filter");
  const newUserForm = document.getElementById("new-user-form");
  const newUserAlert = document.getElementById("new-user-alert");
  const submitUserBtn = document.getElementById("submit-user-btn");

  const editDialog = document.getElementById("edit-user-dialog");
  const editForm = document.getElementById("edit-user-form");
  const editAlert = document.getElementById("edit-user-alert");
  const editSaveBtn = document.getElementById("edit-user-save-btn");
  let editingUserId = null;

  // ---------------- Tabs ----------------
  document.querySelectorAll(".tab-button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");
    });
  });

  function showError(message) {
    alertBox.innerHTML = `<div class="alert alert-error">${message}</div>`;
  }

  // ---------------- Listagem de usuários ----------------
  async function loadUsers() {
    try {
      const users = await Api.listUsers(statusFilter.value || undefined);
      renderUsersTable(users);
    } catch (err) {
      showError(err.message || "Falha ao carregar usuários.");
    }
  }

  function renderUsersTable(users) {
    if (users.length === 0) {
      usersTable.innerHTML = `<p class="empty-state">Nenhum usuário cadastrado ainda.</p>`;
      return;
    }

    usersTable.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Nome</th><th>Matrícula</th><th>Status</th><th>Expira em</th>
            <th>Último acesso</th><th>Ações</th>
          </tr>
        </thead>
        <tbody>
          ${users
            .map(
              (u) => `
            <tr>
              <td data-label="Nome">${u.full_name}</td>
              <td data-label="Matrícula">${u.matricula}</td>
              <td data-label="Status"><span class="${statusBadgeClass(u.status)}">${statusLabel(u.status)}</span></td>
              <td data-label="Expira em">${formatDateTime(u.expires_at)}</td>
              <td data-label="Último acesso">${formatDateTime(u.last_access_at)}</td>
              <td data-label="Ações">
                <div class="actions-cell">
                  ${u.status === "failed" ? `<button class="btn btn-secondary btn-sm" data-action="retry" data-id="${u.id}">Tentar novamente</button>` : ""}
                  ${["active", "failed"].includes(u.status) ? `<button class="btn btn-danger btn-sm" data-action="revoke" data-id="${u.id}">Revogar agora</button>` : ""}
                  ${u.status !== "purged" ? `<button class="btn btn-secondary btn-sm" data-action="edit" data-id="${u.id}">Editar</button>` : ""}
                  <button class="btn btn-danger btn-sm" data-action="delete" data-id="${u.id}">Excluir definitivamente</button>
                </div>
              </td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;

    usersTable.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => handleUserAction(btn.dataset.action, btn.dataset.id, btn));
    });
  }

  async function handleUserAction(action, id, btn) {
    if (action === "edit") {
      openEditDialog(id);
      return;
    }

    const confirmMsg =
      action === "revoke"
        ? "Revogar o acesso deste usuário imediatamente em todos os ambientes?"
        : action === "delete"
          ? "Excluir definitivamente este usuário? Isso remove os dados dele de todos os ambientes (Linux, VPN, Next Term) e apaga o cadastro do banco. Essa ação não pode ser desfeita."
          : null;
    if (confirmMsg && !window.confirm(confirmMsg)) return;

    btn.disabled = true;
    try {
      if (action === "retry") await Api.retryProvisioning(id);
      if (action === "revoke") await Api.revokeNow(id);
      if (action === "delete") await Api.deleteUser(id);
      await loadUsers();
    } catch (err) {
      showError(err.message || "Falha ao executar a ação.");
      btn.disabled = false;
    }
  }

  // ---------------- Edição de usuário ----------------
  async function openEditDialog(id) {
    editAlert.innerHTML = "";
    try {
      const user = await Api.getUser(id);
      editingUserId = id;
      document.getElementById("edit_full_name").value = user.full_name;
      document.getElementById("edit_personal_email").value = user.personal_email;
      document.getElementById("edit_phone").value = user.phone;
      document.getElementById("edit_access_days").value = user.access_days;
      document.getElementById("edit_test_description").value = user.test_description;
      editDialog.showModal();
    } catch (err) {
      showError(err.message || "Falha ao carregar dados do usuário.");
    }
  }

  document.getElementById("edit-user-cancel-btn").addEventListener("click", () => {
    editDialog.close();
  });

  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    editAlert.innerHTML = "";
    editSaveBtn.disabled = true;
    try {
      await Api.updateUser(editingUserId, {
        full_name: document.getElementById("edit_full_name").value.trim(),
        personal_email: document.getElementById("edit_personal_email").value.trim(),
        phone: document.getElementById("edit_phone").value.trim(),
        access_days: Number(document.getElementById("edit_access_days").value),
        test_description: document.getElementById("edit_test_description").value.trim(),
      });
      editDialog.close();
      await loadUsers();
    } catch (err) {
      editAlert.innerHTML = `<div class="alert alert-error">${err.message || "Falha ao salvar alterações."}</div>`;
    } finally {
      editSaveBtn.disabled = false;
    }
  });

  statusFilter.addEventListener("change", loadUsers);
  document.getElementById("refresh-users-btn").addEventListener("click", loadUsers);

  // ---------------- Novo usuário ----------------
  newUserForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    newUserAlert.innerHTML = "";
    submitUserBtn.disabled = true;
    submitUserBtn.textContent = "Cadastrando e provisionando...";

    const formData = new FormData();
    formData.append("full_name", document.getElementById("full_name").value.trim());
    formData.append("matricula", document.getElementById("matricula").value.trim());
    formData.append("personal_email", document.getElementById("personal_email").value.trim());
    formData.append("phone", document.getElementById("phone").value.trim());
    formData.append("test_description", document.getElementById("test_description").value.trim());
    formData.append("access_days", document.getElementById("access_days").value);
    const fileInput = document.getElementById("document");
    if (fileInput.files[0]) formData.append("document", fileInput.files[0]);

    try {
      const created = await Api.createUser(formData);
      newUserAlert.innerHTML = `<div class="alert alert-success">Usuário ${created.full_name} cadastrado com status "${statusLabel(created.status)}".</div>`;
      newUserForm.reset();
      document.getElementById("access_days").value = 30;
      await loadUsers();
      document.querySelector('[data-tab="tab-users"]').click();
    } catch (err) {
      newUserAlert.innerHTML = `<div class="alert alert-error">${err.message || "Falha ao cadastrar usuário."}</div>`;
    } finally {
      submitUserBtn.disabled = false;
      submitUserBtn.textContent = "Cadastrar e provisionar";
    }
  });

  loadUsers();
})();
