(function () {
  renderTopbar("dashboard");

  const alertBox = document.getElementById("alert-box");
  const statsGrid = document.getElementById("stats-grid");
  const envBreakdown = document.getElementById("env-breakdown");
  const recentAccessTable = document.getElementById("recent-access-table");

  function showError(message) {
    alertBox.innerHTML = `<div class="alert alert-error">${message}</div>`;
  }

  function renderStats(stats) {
    const cards = [
      { label: "Usuários ativos", value: stats.active_users, accent: "accent-active" },
      { label: "Aguardando provisionamento", value: stats.pending_users, accent: "accent-pending" },
      { label: "Expirando em 7 dias", value: stats.expiring_in_7_days, accent: "accent-pending" },
      { label: "Revogados (retendo dados)", value: stats.revoked_users, accent: "" },
      { label: "Dados já removidos", value: stats.purged_users, accent: "" },
      { label: "Falhas de provisionamento", value: stats.failed_users, accent: "accent-danger" },
      { label: "Total histórico", value: stats.total_users, accent: "" },
    ];
    statsGrid.innerHTML = cards
      .map(
        (c) => `
        <div class="stat-card ${c.accent}">
          <div class="value">${c.value}</div>
          <div class="label">${c.label}</div>
        </div>`
      )
      .join("");
  }

  function renderEnvBreakdown(byEnv) {
    const envs = Object.keys(byEnv);
    if (envs.length === 0) {
      envBreakdown.innerHTML = `<p class="empty-state">Nenhum provisionamento registrado ainda.</p>`;
      return;
    }
    envBreakdown.innerHTML = `
      <table class="data-table">
        <thead>
          <tr><th>Ambiente</th><th>Sucesso</th><th>Falha</th><th>Revogado</th><th>Removido</th></tr>
        </thead>
        <tbody>
          ${envs
            .map((env) => {
              const s = byEnv[env];
              return `<tr>
                <td data-label="Ambiente">${envLabel(env)}</td>
                <td data-label="Sucesso">${s.success || 0}</td>
                <td data-label="Falha">${s.failed || 0}</td>
                <td data-label="Revogado">${s.revoked || 0}</td>
                <td data-label="Removido">${s.purged || 0}</td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    `;
  }

  async function renderRecentAccess() {
    const users = await Api.listUsers();
    const withAccess = users
      .filter((u) => u.last_access_at)
      .sort((a, b) => new Date(b.last_access_at) - new Date(a.last_access_at))
      .slice(0, 10);

    if (withAccess.length === 0) {
      recentAccessTable.innerHTML = `<p class="empty-state">Ainda não há registros de acesso sincronizados.</p>`;
      return;
    }

    recentAccessTable.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Usuário</th><th>Matrícula</th><th>Status</th><th>Último acesso</th></tr></thead>
        <tbody>
          ${withAccess
            .map(
              (u) => `<tr>
                <td data-label="Usuário">${u.full_name}</td>
                <td data-label="Matrícula">${u.matricula}</td>
                <td data-label="Status"><span class="${statusBadgeClass(u.status)}">${statusLabel(u.status)}</span></td>
                <td data-label="Último acesso">${formatDateTime(u.last_access_at)}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;
  }

  async function loadAll() {
    try {
      const stats = await Api.dashboardStats();
      renderStats(stats);
      renderEnvBreakdown(stats.users_by_environment_status);
      await renderRecentAccess();
    } catch (err) {
      showError(err.message || "Falha ao carregar o painel.");
    }
  }

  document.getElementById("refresh-btn").addEventListener("click", loadAll);
  loadAll();
})();
