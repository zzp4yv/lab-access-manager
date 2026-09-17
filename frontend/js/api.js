/**
 * Cliente HTTP mínimo para a API do backend, com anexação automática do
 * token JWT armazenado após o login e tratamento uniforme de erros.
 */
const API_BASE = "/api";
const TOKEN_KEY = "lab_access_token";
const ADMIN_KEY = "lab_access_admin";

const Auth = {
  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  },
  setSession(token, admin) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(ADMIN_KEY, JSON.stringify(admin));
  },
  getAdmin() {
    try {
      return JSON.parse(localStorage.getItem(ADMIN_KEY) || "null");
    } catch {
      return null;
    }
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ADMIN_KEY);
  },
  requireAuthOrRedirect() {
    if (!this.getToken()) {
      window.location.href = "/index.html";
    }
  },
  logout() {
    this.clear();
    window.location.href = "/index.html";
  },
};

class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function apiRequest(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  const token = Auth.getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });

  if (resp.status === 401) {
    Auth.clear();
    window.location.href = "/index.html";
    throw new ApiError("Sessão expirada", 401, null);
  }

  let payload = null;
  const text = await resp.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!resp.ok) {
    const detail = (payload && payload.detail) || resp.statusText || "Erro na requisição";
    throw new ApiError(detail, resp.status, payload);
  }

  return payload;
}

const Api = {
  login: (email, password) => apiRequest("/auth/login", { method: "POST", body: { email, password } }),
  me: () => apiRequest("/auth/me"),

  listUsers: (statusFilter) =>
    apiRequest(`/users${statusFilter ? `?status_filter=${statusFilter}` : ""}`),
  getUser: (id) => apiRequest(`/users/${id}`),
  createUser: (formData) => apiRequest("/users", { method: "POST", body: formData, isForm: true }),
  updateUser: (id, data) => apiRequest(`/users/${id}`, { method: "PATCH", body: data }),
  deleteUser: (id) => apiRequest(`/users/${id}`, { method: "DELETE" }),
  retryProvisioning: (id) => apiRequest(`/users/${id}/retry-provisioning`, { method: "POST" }),
  revokeNow: (id) => apiRequest(`/users/${id}/revoke-now`, { method: "POST" }),
  runLifecycleNow: () => apiRequest("/users/run-lifecycle-now", { method: "POST" }),

  listAdmins: () => apiRequest("/admins"),
  createAdmin: (data) => apiRequest("/admins", { method: "POST", body: data }),
  updateAdmin: (id, data) => apiRequest(`/admins/${id}`, { method: "PATCH", body: data }),

  dashboardStats: () => apiRequest("/dashboard/stats"),
};

function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function statusLabel(status) {
  const map = {
    pending: "Pendente",
    active: "Ativo",
    revoked: "Revogado",
    purged: "Dados removidos",
    failed: "Falha no provisionamento",
  };
  return map[status] || status;
}

function statusBadgeClass(status) {
  const map = {
    pending: "badge badge-pending",
    active: "badge badge-active",
    revoked: "badge badge-revoked",
    purged: "badge badge-purged",
    failed: "badge badge-failed",
  };
  return map[status] || "badge";
}

function envLabel(env) {
  const map = {
    linux_tars: "Linux (tars)",
    linux_case: "Linux (case)",
    pangolin_vpn: "VPN Pangolin",
    next_term: "Next Term (shell/RDP)",
  };
  return map[env] || env;
}
