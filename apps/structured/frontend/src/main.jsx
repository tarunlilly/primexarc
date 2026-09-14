import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { MsalProvider } from '@azure/msal-react';
import { loadAuthConfig } from '@/lib/auth';
import App from './App.jsx';
import './globals.css';

function ConfigErrorScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center max-w-md px-6">
        <p className="font-nav text-sm font-medium text-destructive mb-2">
          Configuration Error
        </p>
        <p className="font-nav text-sm text-muted-foreground">
          The application cannot authenticate. Contact the platform team to verify the deployment.
        </p>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));

loadAuthConfig()
  .then((msalInstance) =>
    msalInstance.initialize()
      .then(() => msalInstance.handleRedirectPromise())
      .then(() => root.render(
        <React.StrictMode>
          <MsalProvider instance={msalInstance}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </MsalProvider>
        </React.StrictMode>
      ))
  )
  .catch(() => root.render(
    <React.StrictMode>
      <ConfigErrorScreen />
    </React.StrictMode>
  ));
