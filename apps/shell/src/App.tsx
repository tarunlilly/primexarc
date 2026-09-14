import { Routes, Route } from 'react-router-dom'
import { UserProvider } from '@/lib/user-context'
import Layout from '@/components/Layout'
import Landing from '@/pages/Landing'
import HelpCenter from '@/pages/HelpCenter'
import Support from '@/pages/Support'
import Account from '@/pages/Account'
import NotFound from '@/pages/NotFound'

export default function App() {
  return (
    <UserProvider>
      <Routes>
        <Route
          path="/"
          element={
            <Layout variant="white">
              <Landing />
            </Layout>
          }
        />
        <Route
          path="/help"
          element={
            <Layout variant="white">
              <HelpCenter />
            </Layout>
          }
        />
        <Route
          path="/support"
          element={
            <Layout variant="white">
              <Support />
            </Layout>
          }
        />
        <Route
          path="/account"
          element={
            <Layout variant="white">
              <Account />
            </Layout>
          }
        />
        <Route
          path="*"
          element={
            <Layout variant="white">
              <NotFound />
            </Layout>
          }
        />
      </Routes>
    </UserProvider>
  )
}
