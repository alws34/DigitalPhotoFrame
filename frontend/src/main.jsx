import React from 'react'
import ReactDOM from 'react-dom/client'
import axios from 'axios'
import App from './App.jsx'
import './index.css'

// Send the session cookie with every request and echo the CSRF token that
// the backend exposes via the JS-readable XSRF-TOKEN cookie.
axios.defaults.withCredentials = true
axios.defaults.xsrfCookieName = 'XSRF-TOKEN'
axios.defaults.xsrfHeaderName = 'X-CSRF-Token'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
