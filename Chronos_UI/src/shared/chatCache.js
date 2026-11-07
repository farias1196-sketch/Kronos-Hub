const DATABASE_NAME = "chronos-ui-cache";
const STORE_NAME = "chat-pages";
const VERSION = 1;
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DATABASE_NAME, VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function cacheKey(tenant, resource) {
  return `${tenant}:${resource}`;
}

export async function readChatCache(tenant, resource) {
  if (!window.indexedDB) return null;
  const db = await openDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(cacheKey(tenant, resource));
      request.onsuccess = () => {
        const record = request.result;
        resolve(record && Date.now() - record.savedAt < MAX_AGE_MS ? record.value : null);
      };
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

export async function writeChatCache(tenant, resource, value) {
  if (!window.indexedDB) return;
  const db = await openDatabase();
  try {
    await new Promise((resolve, reject) => {
      const request = db.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME).put({
        key: cacheKey(tenant, resource),
        savedAt: Date.now(),
        value,
      });
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

export async function clearChatCache() {
  if (!window.indexedDB) return;
  const db = await openDatabase();
  try {
    await new Promise((resolve, reject) => {
      const request = db.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME).clear();
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}
