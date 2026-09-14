
import { Link } from 'react-router-dom'
import { Footer } from '@/components/Footer'
import { 
  FileText,
  ArrowLeft
} from 'lucide-react'

// Constants
const LAST_UPDATED = new Date().toLocaleDateString('en-US', { 
  year: 'numeric', 
  month: 'long', 
  day: 'numeric' 
})

// Component: Terms Section
interface TermsSectionProps {
  readonly id: string
  readonly title: string
  readonly children: React.ReactNode
}

function TermsSection({ id, title, children }: TermsSectionProps) {
  return (
    <section id={id} className="mt-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">{title}</h2>
      {children}
    </section>
  )
}

/**
 * Terms and Conditions Page Component
 * 
 * Displays legal terms and conditions for PrimeData platform.
 * Follows enterprise best practices with proper accessibility
 * and semantic HTML structure.
 */
export default function TermsPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-white to-rose-100 flex flex-col">

      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center space-x-2">
              <ArrowLeft className="h-5 w-5 text-gray-600 hover:text-gray-900 transition-colors" />
              <span className="text-sm text-gray-600 hover:text-gray-900 transition-colors">Back to Home</span>
            </Link>
            <Link to="/" className="text-2xl font-bold bg-gradient-to-r from-[#C8102E] via-[#C8102E] to-[#A00D24] bg-clip-text text-transparent">
              PrimeData
            </Link>
            <div className="w-24"></div> {/* Spacer for centering */}
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-4 py-16 max-w-4xl">
        <article className="bg-white rounded-2xl shadow-lg border-2 border-gray-100 p-8 md:p-12">
          {/* Header */}
          <header className="flex items-center mb-8">
            <div className="w-12 h-12 bg-gradient-to-br from-[#C8102E] to-[#A00D24] rounded-xl flex items-center justify-center mr-4">
              <FileText className="h-6 w-6 text-white" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-gray-900">Terms and Conditions</h1>
              <p className="text-gray-600 mt-2">
                Last updated: <time dateTime={LAST_UPDATED}>{LAST_UPDATED}</time>
              </p>
            </div>
          </header>

          {/* Content */}
          <div className="prose prose-lg max-w-none space-y-8 text-gray-700">
            <TermsSection id="acceptance" title="1. Acceptance of Terms">
              <p>
                By accessing and using PrimeData ("Service"), you accept and agree to be bound by the terms and provision of this agreement. 
                If you do not agree to abide by the above, please do not use this service.
              </p>
            </TermsSection>

            <TermsSection id="use-license" title="2. Use License">
              <p>
                Permission is granted to temporarily use PrimeData for personal and commercial purposes. This is the grant of a license, not a transfer of title, and under this license you may not:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                <li>Modify or copy the materials</li>
                <li>Use the materials for any commercial purpose or for any public display</li>
                <li>Attempt to reverse engineer any software contained in PrimeData</li>
                <li>Remove any copyright or other proprietary notations from the materials</li>
                <li>Transfer the materials to another person or "mirror" the materials on any other server</li>
              </ul>
            </TermsSection>

            <TermsSection id="service-description" title="3. Service Description">
              <p>
                PrimeData provides an enterprise AI data platform that enables users to ingest, process, validate, and vectorize data for AI applications. 
                We reserve the right to modify, suspend, or discontinue any aspect of the Service at any time.
              </p>
            </TermsSection>

            <TermsSection id="user-accounts" title="4. User Accounts and Responsibilities">
              <p>
                You are responsible for maintaining the confidentiality of your account credentials and for all activities that occur under your account. 
                You agree to:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                <li>Provide accurate and complete information when creating an account</li>
                <li>Maintain and update your account information</li>
                <li>Notify us immediately of any unauthorized use of your account</li>
                <li>Be responsible for all content uploaded through your account</li>
              </ul>
            </TermsSection>

            <TermsSection id="data-privacy" title="5. Data and Privacy">
              <p>
                Your use of PrimeData is also governed by our Privacy Policy. Please review our{' '}
                <Link to="/privacy" className="text-[#C8102E] hover:text-[#A00D24] underline">
                  Privacy Policy
                </Link>, which also governs your use of the Service, 
                to understand our practices. You retain all rights to your data, and we will not use your data except as necessary to provide the Service.
              </p>
            </TermsSection>

            <TermsSection id="payment-billing" title="6. Payment and Billing">
              <p>
                If you purchase a subscription, you agree to pay all fees associated with your selected plan. Fees are billed in advance on a monthly or annual basis. 
                All fees are non-refundable except as required by law. We reserve the right to change our pricing with 30 days' notice.
              </p>
            </TermsSection>

            <TermsSection id="intellectual-property" title="7. Intellectual Property">
              <p>
                The Service and its original content, features, and functionality are and will remain the exclusive property of PrimeData and its licensors. 
                The Service is protected by copyright, trademark, and other laws. Our trademarks and trade dress may not be used without our prior written consent.
              </p>
            </TermsSection>

            <TermsSection id="limitation-liability" title="8. Limitation of Liability">
              <p>
                In no event shall PrimeData, nor its directors, employees, partners, agents, suppliers, or affiliates, be liable for any indirect, incidental, special, 
                consequential, or punitive damages, including without limitation, loss of profits, data, use, goodwill, or other intangible losses, resulting from your use of the Service.
              </p>
            </TermsSection>

            <TermsSection id="termination" title="9. Termination">
              <p>
                We may terminate or suspend your account and bar access to the Service immediately, without prior notice or liability, under our sole discretion, 
                for any reason whatsoever and without limitation, including but not limited to a breach of the Terms.
              </p>
            </TermsSection>

            <TermsSection id="changes" title="10. Changes to Terms">
              <p>
                We reserve the right, at our sole discretion, to modify or replace these Terms at any time. If a revision is material, we will provide at least 30 days' 
                notice prior to any new terms taking effect. What constitutes a material change will be determined at our sole discretion.
              </p>
            </TermsSection>

            <TermsSection id="contact" title="11. Contact Information">
              <p>
                If you have any questions about these Terms and Conditions, please contact us at{' '}
                <Link to="/contact" className="text-[#C8102E] hover:text-[#A00D24] underline">
                  our contact page
                </Link>.
              </p>
            </TermsSection>
          </div>
        </article>
      </main>

      <Footer />
    </div>
  )
}

