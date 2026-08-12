/**
 * Foundation home page for the Smart RAG frontend scaffold.
 *
 * Phase 1 Packet 2 only proves a production-buildable App Router shell.
 * Authentication, chat, retrieval, and Stitch UX are intentionally absent.
 */
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <div className={styles.intro}>
          <h1>Smart RAG</h1>
          <p>
            Phase 1 foundation frontend scaffold. Auth, retrieval, and chat are
            not implemented in this packet.
          </p>
        </div>
      </main>
    </div>
  );
}
