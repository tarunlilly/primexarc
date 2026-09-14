import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { getCachedUser } from '@/lib/bouncer-auth'
import App from './App'
import './globals.css'

// Kick off the user fetch before React renders so the session is
// already resolving by the time UserProvider mounts.
getCachedUser()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
