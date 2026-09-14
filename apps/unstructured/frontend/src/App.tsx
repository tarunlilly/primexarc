import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Providers } from '../app/providers'

// Public / marketing pages
import DashboardPage from '../app/dashboard/page'
import FeaturesPage from '../app/features/page'
import PricingPage from '../app/pricing/page'
import ContactPage from '../app/contact/page'
import HelpPage from '../app/help/page'
import PrivacyPage from '../app/privacy/page'
import TermsPage from '../app/terms/page'
import AccountPage from '../app/account/page'

// Protected app pages
import AnalyticsPage from '../app/app/analytics/page'
import BillingPage from '../app/app/billing/page'
import DataSourcesPage from '../app/app/datasources/page'
import PlaybooksPage from '../app/app/playbooks/page'
import ProductsPage from '../app/app/products/page'
import NewProductPage from '../app/app/products/new/page'
import CostEstimatePage from '../app/app/products/cost-estimate/page'
import ProductDetailPage from '../app/app/products/[id]/page'
import ProductEditPage from '../app/app/products/[id]/edit/page'
import NewDatasourcePage from '../app/app/products/[id]/datasources/new/page'
import EditDatasourcePage from '../app/app/products/[id]/datasources/[datasourceId]/edit/page'
import AIReadinessPage from '../app/app/products/[id]/ai-readiness/page'
import PlaygroundPage from '../app/app/products/[id]/playground/page'
import PipelineMetricsPage from '../app/app/products/[id]/pipeline-metrics/page'
import PipelineRunsPage from '../app/app/products/[id]/pipeline-runs/page'
import LineagePage from '../app/app/products/[id]/lineage/page'
import SettingsPage from '../app/app/settings/page'
import SupportPage from '../app/app/support/page'
import SystemHealthPage from '../app/app/system/health/page'
import TeamPage from '../app/app/team/page'

export default function App() {
  return (
    <BrowserRouter>
      <Providers>
        <Routes>
          {/* Root redirects to /dashboard */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Marketing / public pages */}
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/features" element={<FeaturesPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/contact" element={<ContactPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/account" element={<AccountPage />} />

          {/* Protected app routes */}
          <Route path="/app/analytics" element={<AnalyticsPage />} />
          <Route path="/app/billing" element={<BillingPage />} />
          <Route path="/app/datasources" element={<DataSourcesPage />} />
          <Route path="/app/playbooks" element={<PlaybooksPage />} />
          <Route path="/app/settings" element={<SettingsPage />} />
          <Route path="/app/support" element={<SupportPage />} />
          <Route path="/app/team" element={<TeamPage />} />
          <Route path="/app/system/health" element={<SystemHealthPage />} />

          {/* Products */}
          <Route path="/app/products" element={<ProductsPage />} />
          <Route path="/app/products/new" element={<NewProductPage />} />
          <Route path="/app/products/cost-estimate" element={<CostEstimatePage />} />
          <Route path="/app/products/:id" element={<ProductDetailPage />} />
          <Route path="/app/products/:id/edit" element={<ProductEditPage />} />
          <Route path="/app/products/:id/datasources/new" element={<NewDatasourcePage />} />
          <Route path="/app/products/:id/datasources/:datasourceId/edit" element={<EditDatasourcePage />} />
          <Route path="/app/products/:id/ai-readiness" element={<AIReadinessPage />} />
          <Route path="/app/products/:id/playground" element={<PlaygroundPage />} />
          <Route path="/app/products/:id/pipeline-metrics" element={<PipelineMetricsPage />} />
          <Route path="/app/products/:id/pipeline-runs" element={<PipelineRunsPage />} />
          <Route path="/app/products/:id/lineage" element={<LineagePage />} />

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Providers>
    </BrowserRouter>
  )
}
