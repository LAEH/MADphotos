import { initializeApp } from 'firebase/app'
import { getFirestore, collection, addDoc, serverTimestamp } from 'firebase/firestore'

const firebaseConfig = {
  apiKey: "AIzaSyBVFSttlVE3gL78fEqL8c5rwwMplJxfSVg",
  authDomain: "laeh380to760.firebaseapp.com",
  projectId: "laeh380to760",
  storageBucket: "laeh380to760.firebasestorage.app",
  messagingSenderId: "116107774294",
  appId: "1:116107774294:web:c815f367ce3cc6f9536ef7"
}

const app = initializeApp(firebaseConfig)
const db = getFirestore(app)

export function fireAndForget(collectionName: string, data: Record<string, unknown>): void {
  addDoc(collection(db, collectionName), {
    ...data,
    ts: serverTimestamp(),
  }).catch(() => {})
}

export { db, serverTimestamp }
