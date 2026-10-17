/**
 * authFetch - Wrapper autour de fetch injectant automatiquement le token JWT
 * depuis localStorage ('rockib_token'). En cas d'erreur 401, purge le token
 * et émet un événement 'rockib:unauthorized' pour inviter l'utilisateur à se connecter.
 */
export async function authFetch(url, options = {}) {
  const token = localStorage.getItem('rockib_token');
  const headers = { ...(options.headers || {}) };

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    localStorage.removeItem('rockib_token');
    window.dispatchEvent(new CustomEvent('rockib:unauthorized'));
  }

  return response;
}
