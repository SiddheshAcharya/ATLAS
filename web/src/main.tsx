import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
// Bundled, not fetched from Google Fonts: demo runs must work with the network unplugged.
import '@fontsource/cormorant-garamond/500.css'
import '@fontsource/cormorant-garamond/500-italic.css'
import '@fontsource/cormorant-garamond/600.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
