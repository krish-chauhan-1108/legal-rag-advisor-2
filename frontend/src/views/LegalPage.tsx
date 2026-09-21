import { Link, useLocation } from 'react-router-dom';
import { ArrowLeft, Scale } from 'lucide-react';

const lastUpdated = 'September 21, 2026';

export function LegalPage() {
  const { pathname } = useLocation();
  const isPrivacy = pathname === '/privacy';

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
          <p className="legal-page__eyebrow">{isPrivacy ? 'Privacy Policy' : 'Terms of Service'}</p>
          <h1>{isPrivacy ? 'Your privacy matters.' : 'Clear terms for using TRANA.'}</h1>
          <p className="legal-page__updated">Last updated: {lastUpdated}</p>

        {isPrivacy ? (
          <>
            <p>TRANA is a legal research assistant that helps users explore an indexed collection of legal documents. This policy explains what information we collect and how we use it.</p>
            <h2>Information we collect</h2>
            <p>When you sign in with Google, we receive your name, email address, profile image, and the Google account identifier needed to authenticate your account. We store your chat prompts, generated responses, and chat titles so your history can be restored across sessions.</p>
            <h2>How we use information</h2>
            <p>We use this information to provide authentication, save and display your chat history, operate TRANA, and protect the service. We do not sell personal information or use Google account data for advertising.</p>
            <h2>Documents and AI processing</h2>
            <p>Documents attached to an individual query are used only for that query and are not added to TRANA's shared indexed knowledge base. Prompts and attached content may be processed by the AI providers configured for the service in order to generate a response.</p>
            <h2>Storage and retention</h2>
            <p>Account and chat data are stored in the service's hosted database. We retain chat history until it is deleted through the service or a deletion request is processed.</p>
            <h2>Contact</h2>
            <p>For privacy questions or deletion requests, contact <a href="mailto:ckhraiushh1@gmail.com">ckhraiushh1@gmail.com</a>.</p>
          </>
        ) : (
          <>
            <p>TRANA is provided for legal research and information purposes only. It is not a law firm, does not provide legal advice, and does not create an attorney-client relationship.</p>
            <h2>Acceptable use</h2>
            <p>You may use TRANA only for lawful purposes. Do not upload confidential, privileged, or highly sensitive information unless you are authorised to do so. You are responsible for checking the accuracy and currency of any output before relying on it.</p>
            <h2>AI-generated information</h2>
            <p>TRANA's responses may be incomplete, inaccurate, or out of date. They should not replace advice from a qualified legal professional or the text of applicable law.</p>
            <h2>Availability</h2>
            <p>We may change, suspend, or discontinue features of TRANA. The service is provided on an “as is” and “as available” basis to the extent permitted by law.</p>
            <h2>Contact</h2>
            <p>Questions about these terms can be sent to <a href="mailto:ckhraiushh1@gmail.com">ckhraiushh1@gmail.com</a>.</p>
          </>
        )}

          <div className="legal-page__footer"><Link to="/privacy">Privacy Policy</Link><span>·</span><Link to="/terms">Terms of Service</Link><span>·</span><Link to="/">Return to TRANA</Link></div>
        </article>
      </div>
    </main>
  );
}
