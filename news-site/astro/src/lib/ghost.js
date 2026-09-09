import GhostContentAPI from '@tryghost/content-api';

const api = process.env.GHOST_CONTENT_API_KEY
  ? new GhostContentAPI({
      url: process.env.GHOST_CONTENT_API_URL,
      key: process.env.GHOST_CONTENT_API_KEY,
      version: 'v5.0',
    })
  : null;

export async function getPosts({ limit = 10 } = {}) {
  if (!api) {
    return { posts: [], placeholder: true };
  }
  return api.posts.browse({ limit, include: ['tags', 'authors'] });
}

export async function getPost(slug) {
  if (!api) return null;
  try {
    return await api.posts.read({ slug, include: ['tags', 'authors'] });
  } catch {
    return null;
  }
}