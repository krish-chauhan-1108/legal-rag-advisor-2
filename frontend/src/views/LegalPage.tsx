import { Link, useLocation } from 'react-router-dom';
import { ArrowLeft, FileText, Scale, ShieldCheck } from 'lucide-react';

const lastUpdated = 'September 21, 2026';

export function LegalPage() {
  const { pathname } = useLocation();
  const isPrivacy = pathname === '/privacy';
  const sections = isPrivacy
    ? [
        ['information', 'Information we collect'],
        ['use', 'How we use information'],
        ['processing', 'Documents and AI processing'],
        ['storage', 'Storage and retention'],
        ['contact', 'Contact'],
      ]
    : [
        ['use', 'Acceptable use'],
        ['ai', 'AI-generated information'],
        ['availability', 'Availability'],
        ['contact', 'Contact'],
      ];

  return (
    <main className="legal-page">
      <div className="legal-page__inner">
        <div className="legal-page__topbar">
          <Link to="/home" className="legal-page__brand">
            <Scale className="h-5 w-5" strokeWidth={1.5} />
            TRANA
          </Link>
          <Link to="/" className="legal-page__back"><ArrowLeft className="h-4 w-4" /> Back to chats</Link>
        </div>

        <article className="legal-page__card">
          <header className="legal-page__hero">
            <div className="legal-page__hero-icon">
              {isPrivacy ? <ShieldCheck strokeWidth={1.5} /> : <FileText strokeWidth={1.5} />}
            </div>
            <div>
              <p className="legal-page__eyebrow">{isPrivacy ? 'Privacy Policy' : 'Terms of Service'}</p>
              <h1>{isPrivacy ? 'Your privacy matters.' : 'Clear terms for using TRANA.'}</h1>
              <p className="legal-page__summary">
                {isPrivacy
                  ? 'A plain-language overview of the information TRANA handles and the choices you have.'
                  : 'The boundaries and responsibilities that keep TRANA useful, safe, and clear.'}
              </p>
              <p className="legal-page__updated"><span>Effective</span> {lastUpdated}</p>
            </div>
          </header>

          <div className="legal-page__content">
            <aside className="legal-page__toc" aria-label="On this page">
              <p className="legal-page__toc-label">On this page</p>
              <nav>
                {sections.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
              </nav>
              <div className="legal-page__aside-note">
                <span>Questions?</span>
                <a href="mailto:ckhraiushh1@gmail.com">Contact the TRANA team</a>
              </div>
            </aside>

            <div className="legal-page__body">
              {isPrivacy ? (
                <>
                  <section id="overview">
                    <p className="legal-page__lead">TRANA is a legal research assistant that helps users explore an indexed collection of legal documents. This policy explains what information we collect and how we use it.</p>
                  </section>
                  <section id="information"><h2>Information we collect</h2><p>When you sign in with Google, we receive your name, email address, profile image, and the Google account identifier needed to authenticate your account. Signed-in chat prompts, generated responses, and chat titles are stored so your history can be restored across sessions. Temporary chats are stored in your browser and sent to our service for processing, but are not saved to server-side chat history.</p></section>
                  <section id="use"><h2>How we use information</h2><p>We use this information to provide authentication, save and display your chat history, operate TRANA, and protect the service. We do not sell personal information or use Google account data for advertising.</p></section>
                  <section id="processing"><h2>Documents and AI processing</h2><p>PDFs and images attached to a chat are used to answer questions in that chat and are not added to TRANA's shared indexed legal library. Prompts and attached content may be processed by the AI providers configured for the service in order to generate a response.</p></section>
                  <section id="storage"><h2>Storage and retention</h2><p>Account chats and uploaded attachment data are stored by the service. Attachments remain associated with their chat so they can be used for follow-up questions. We retain saved chat history and its attachments until the chat is deleted through the service or a deletion request is processed. Temporary chat history is stored in your browser until you start a new chat or clear your browser storage.</p></section>
                  <section id="contact"><h2>Contact</h2><p>For privacy questions or deletion requests, contact <a href="mailto:ckhraiushh1@gmail.com">ckhraiushh1@gmail.com</a>.</p></section>
                </>
              ) : (
                <>
                  <section id="overview">
                    <p className="legal-page__lead">TRANA is provided for legal research and information purposes only. It is not a law firm, does not provide legal advice, and does not create an attorney-client relationship.</p>
                  </section>
                  <section id="use"><h2>Acceptable use</h2><p>You may use TRANA only for lawful purposes. Do not upload confidential, privileged, or highly sensitive information unless you are authorised to do so. You are responsible for checking the accuracy and currency of any output before relying on it.</p></section>
                  <section id="ai"><h2>AI-generated information</h2><p>TRANA's responses may be incomplete, inaccurate, or out of date. They should not replace advice from a qualified legal professional or the text of applicable law.</p></section>
                  <section id="availability"><h2>Availability</h2><p>We may change, suspend, or discontinue features of TRANA. The service is provided on an “as is” and “as available” basis to the extent permitted by law.</p></section>
                  <section id="contact"><h2>Contact</h2><p>Questions about these terms can be sent to <a href="mailto:ckhraiushh1@gmail.com">ckhraiushh1@gmail.com</a>.</p></section>
                </>
              )}
            </div>
          </div>

          <footer className="legal-page__footer"><Link to="/privacy">Privacy Policy</Link><span>·</span><Link to="/terms">Terms of Service</Link><span>·</span><Link to="/">Return to TRANA</Link></footer>
        </article>
      </div>
    </main>
  );
}
