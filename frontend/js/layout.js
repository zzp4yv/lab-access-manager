/**
 * Renderiza a barra superior comum a todas as páginas autenticadas e
 * garante que apenas administradores logados acessem a página.
 */
function renderTopbar(activePage) {
  Auth.requireAuthOrRedirect();
  const admin = Auth.getAdmin();

  const links = [
    { href: "/dashboard.html", key: "dashboard", label: "Painel" },
    { href: "/users.html", key: "users", label: "Usuários & Administradores" },
  ];

  const navHtml = links
    .map(
      (l) =>
        `<a href="${l.href}" class="${l.key === activePage ? "active" : ""}">${l.label}</a>`
    )
    .join("");

  document.getElementById("topbar-root").innerHTML = `
    <div class="topbar">
      <div class="brand">🧪 Instituto Oxigênio — Acessos ao Laboratório</div>
      <nav>${navHtml}</nav>
      <div class="user-info">
        <span>${admin ? admin.full_name : ""}</span>
        <button class="link-button" id="logout-btn">Sair</button>
      </div>
    </div>
  `;

  document.getElementById("logout-btn").addEventListener("click", () => Auth.logout());
}
