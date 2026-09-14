import { Routes, Route, Link } from 'react-router-dom';
import { MsalAuthenticationTemplate } from '@azure/msal-react';
import { InteractionType } from '@azure/msal-browser';
import Home from '@/pages/Home.jsx';
import Assess from '@/pages/Assess.jsx';
import Support from '@/pages/Support.jsx';
import Account from '@/pages/Account.jsx';
import History from '@/pages/History.jsx';
import AssessRunView from '@/pages/AssessRunView.jsx';
import Console from '@/pages/Console.jsx';
import HelpCenter from '@/pages/HelpCenter.jsx';
import Layout from '@/Layout.jsx';
import { Button } from '@/components/ui/button';
import { loginRequest } from '@/lib/auth';

function AuthLoading() {
  return null;
}

function AuthError({ error }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <p className="font-nav text-sm font-medium text-muted-foreground mb-2">
          Authentication failed
        </p>
        <p className="font-nav text-xs text-destructive">{error?.message}</p>
      </div>
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Layout variant="red">
            <Home />
          </Layout>
        }
      />
      {/* Assess owns its own Layout: variant flips per wizard step */}
      <Route path="/assess" element={<Assess />} />
      {/* History run detail owns its own Layout (wraps Dashboard) */}
      <Route path="/assess/:runId" element={<AssessRunView />} />
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
        path="/history"
        element={
          <Layout variant="white">
            <History />
          </Layout>
        }
      />
      <Route
        path="/console"
        element={
          <Layout variant="white">
            <Console />
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
  );
}

function NotFound() {
  return (
    <section className="container py-32 text-center animate-card-rise">
      <p className="font-nav text-[14px] font-medium text-muted-foreground">
        404 · Not Found
      </p>
      <h1 className="font-display text-7xl md:text-8xl font-light text-primary tracking-tight mt-4 mb-3">
        Lost the trail.
      </h1>
      <p className="text-muted-foreground max-w-md mx-auto mb-8">
        That page doesn't exist yet. Head back to the start.
      </p>
      <Button asChild>
        <Link to="/">Return Home</Link>
      </Button>
    </section>
  );
}

export default function App() {
  return (
    <MsalAuthenticationTemplate
      interactionType={InteractionType.Redirect}
      authenticationRequest={loginRequest}
      errorComponent={AuthError}
      loadingComponent={AuthLoading}
    >
      <AppRoutes />
    </MsalAuthenticationTemplate>
  );
}
