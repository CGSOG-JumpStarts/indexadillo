# 📚 Indexadillo API Documentation Deployment Guide

This guide shows you how to deploy your OpenAPI documentation as a beautiful, interactive Swagger UI site.

## 📁 File Structure

Make sure you have the following structure in your project:

```
indexadillo/
├── docs/
│   ├── index.html             # Swagger UI HTML
│   ├── openapi.yaml           # OpenAPI specification
│   ├── favicon.ico            # Optional: Custom favicon
│   └── assets/                # Optional: Custom CSS/JS
│       ├── custom.css
│       └── logo.png
├── .github/
│   └── workflows/
│       └── deploy-docs.yml    # GitHub Actions deployment
└── netlify.toml               # Netlify configuration
```

## 🚀 Deployment Options

### 1. GitHub Pages (Free & Easy)

**Step 1:** Push your docs to a GitHub repository

```bash
# Add files to your repo
git add docs/
git commit -m "Add API documentation"
git push origin main
```

**Step 2:** Enable GitHub Pages
1. Go to your repo → Settings → Pages
2. Source: Deploy from a branch
3. Branch: `main` 
4. Folder: `/docs`
5. Save

**Step 3:** Access your docs at:
```
https://yourusername.github.io/your-repo-name/
```

#### GitHub Actions Auto-Deploy

Create `.github/workflows/deploy-docs.yml`:

```yaml
name: Deploy API Documentation

on:
  push:
    branches: [ main ]
    paths: [ 'docs/**' ]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        
      - name: Setup Pages
        uses: actions/configure-pages@v4
        
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: './docs'
          
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### 2. Netlify (Recommended for Custom Domains)

**Step 1:** Create `netlify.toml` in your root directory:

```toml
[build]
  publish = "docs"
  
[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-XSS-Protection = "1; mode=block"
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"

[[headers]]
  for = "/openapi.yaml"
  [headers.values]
    Content-Type = "application/x-yaml"

[[redirects]]
  from = "/swagger"
  to = "/"
  status = 301

[[redirects]]
  from = "/api-docs"
  to = "/"
  status = 301

# SPA redirect for client-side routing
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

**Step 2:** Deploy to Netlify
1. Connect your GitHub repo to Netlify
2. Build command: (leave empty)
3. Publish directory: `docs`
4. Deploy!

**Step 3:** Configure custom domain (optional)
- Add your custom domain in Netlify settings
- Update DNS records as instructed

### 3. Vercel (Modern & Fast)

**Step 1:** Create `vercel.json` in your root:

```json
{
  "version": 2,
  "public": true,
  "github": {
    "enabled": false
  },
  "functions": {},
  "routes": [
    {
      "src": "/openapi.yaml",
      "headers": {
        "Content-Type": "application/x-yaml"
      }
    },
    {
      "src": "/(.*)",
      "dest": "/docs/$1"
    }
  ],
  "cleanUrls": true,
  "trailingSlash": false
}
```

**Step 2:** Deploy with Vercel CLI:

```bash
npm i -g vercel
vercel --prod
```

### 4. Azure Static Web Apps

**Step 1:** Create `staticwebapp.config.json` in docs folder:

```json
{
  "routes": [
    {
      "route": "/openapi.yaml",
      "headers": {
        "Content-Type": "application/x-yaml"
      }
    }
  ],
  "navigationFallback": {
    "rewrite": "/index.html",
    "exclude": ["/openapi.yaml", "/*.{css,js,png,jpg,gif,ico,svg}"]
  },
  "responseOverrides": {
    "404": {
      "rewrite": "/index.html"
    }
  }
}
```

**Step 2:** Deploy via GitHub Actions or Azure Portal

### 5. AWS S3 + CloudFront (Enterprise)

**Step 1:** Create S3 bucket for static hosting

**Step 2:** Upload docs folder contents

**Step 3:** Configure CloudFront distribution

**Step 4:** Add custom domain with Route 53

## 🎨 Customization Options

### Custom Styling

Create `docs/assets/custom.css`:

```css
/* Custom theme colors */
:root {
  --primary-color: #667eea;
  --secondary-color: #764ba2;
  --success-color: #10b981;
  --warning-color: #f59e0b;
  --danger-color: #ef4444;
}

/* Custom logo */
.swagger-ui .topbar .link img {
  content: url('./logo.png');
  width: 120px;
  height: auto;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .swagger-ui {
    filter: invert(1) hue-rotate(180deg);
  }
  
  .swagger-ui img {
    filter: invert(1) hue-rotate(180deg);
  }
}
```

### Custom JavaScript

Create `docs/assets/custom.js`:

```javascript
// Custom analytics
function trackAPICall(endpoint) {
  gtag('event', 'api_call', {
    'endpoint': endpoint,
    'source': 'documentation'
  });
}

// Enhanced search
function enhanceSearch() {
  const searchInput = document.querySelector('.filter-container input');
  if (searchInput) {
    searchInput.placeholder = '🔍 Search endpoints... (Ctrl+K)';
  }
}

// Auto-expand popular endpoints
window.addEventListener('load', () => {
  // Auto-expand pipeline and search sections
  setTimeout(() => {
    const pipelineSection = document.querySelector('[data-tag="Pipeline"]');
    const searchSection = document.querySelector('[data-tag="Search"]');
    
    if (pipelineSection) pipelineSection.click();
    if (searchSection) searchSection.click();
  }, 1000);
});
```

### Environment-Specific Configuration

Create multiple OpenAPI specs for different environments:

```
docs/
├── openapi.yaml           # Production
├── openapi-staging.yaml   # Staging
└── openapi-local.yaml     # Local development
```

Modify the HTML to load the appropriate spec:

```javascript
const environment = window.location.hostname;
let specUrl = './openapi.yaml';

if (environment.includes('staging')) {
  specUrl = './openapi-staging.yaml';
} else if (environment.includes('localhost')) {
  specUrl = './openapi-local.yaml';
}

const ui = SwaggerUIBundle({
  url: specUrl,
  // ... other config
});
```

## 🔧 Advanced Features

### 1. API Key Testing

Add a test API key for documentation:

```javascript
// Auto-fill test API key for demos
window.addEventListener('load', () => {
  setTimeout(() => {
    const authButton = document.querySelector('.auth-wrapper .btn.authorize');
    if (authButton) {
      authButton.onclick = () => {
        setTimeout(() => {
          const apiKeyInput = document.querySelector('input[name="X-API-Key"]');
          if (apiKeyInput && !apiKeyInput.value) {
            apiKeyInput.value = 'demo_key_for_testing';
            apiKeyInput.dispatchEvent(new Event('change'));
          }
        }, 100);
      };
    }
  }, 1000);
});
```

### 2. Real-time API Status

```javascript
// Show API status in the header
async function showApiStatus() {
  try {
    const response = await fetch('https://api.indexadillo.ai/v1/health');
    const status = await response.json();
    
    const statusElement = document.createElement('div');
    statusElement.innerHTML = `
      <div style="background: ${status.status === 'healthy' ? '#10b981' : '#ef4444'}; 
                  color: white; padding: 5px 10px; text-align: center; font-size: 12px;">
        API Status: ${status.status.toUpperCase()} 
        ${status.status === 'healthy' ? '✅' : '❌'}
      </div>
    `;
    
    document.body.insertBefore(statusElement, document.body.firstChild);
  } catch (error) {
    console.log('Could not fetch API status');
  }
}

window.addEventListener('load', showApiStatus);
```

### 3. Usage Analytics

```javascript
// Track which endpoints are most viewed
function trackEndpointViews() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const operationId = entry.target.getAttribute('data-operation-id');
        if (operationId) {
          gtag('event', 'endpoint_view', {
            'operation_id': operationId,
            'source': 'documentation'
          });
        }
      }
    });
  });

  document.querySelectorAll('.opblock').forEach(block => {
    observer.observe(block);
  });
}
```

## 🔐 Security Considerations

### 1. Hide Sensitive Information

```yaml
# In your OpenAPI spec, use examples instead of real data
servers:
  - url: https://api.indexadillo.ai/v1
    description: Production API
  # Don't expose internal URLs in public docs
```

### 2. Content Security Policy

Add to your HTML head:

```html
<meta http-equiv="Content-Security-Policy" content="
  default-src 'self';
  script-src 'self' 'unsafe-inline' https://unpkg.com;
  style-src 'self' 'unsafe-inline' https://unpkg.com;
  connect-src 'self' https://api.indexadillo.ai;
  img-src 'self' data: https:;
">
```

## 📊 Monitoring & Analytics

### Google Analytics 4

```html
<!-- Add to your HTML head -->
<script async src="https://www.googletagmanager.com/gtag/js?id=GA_MEASUREMENT_ID"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'GA_MEASUREMENT_ID');
</script>
```

### Hotjar (User Behavior)

```html
<!-- Add to your HTML head -->
<script>
    (function(h,o,t,j,a,r){
        h.hj=h.hj||function(){(h.hj.q=h.hj.q||[]).push(arguments)};
        h._hjSettings={hjid:YOUR_HOTJAR_ID,hjsv:6};
        a=o.getElementsByTagName('head')[0];
        r=o.createElement('script');r.async=1;
        r.src=t+h._hjSettings.hjid+j+h._hjSettings.hjsv;
        a.appendChild(r);
    })(window,document,'https://static.hotjar.com/c/hotjar-','.js?sv=');
</script>
```

## 🚀 Best Practices

1. **Keep specs up to date**: Automate OpenAPI generation from your code
2. **Test examples**: Ensure all examples actually work
3. **Monitor usage**: Track which endpoints are most popular
4. **Gather feedback**: Add feedback widgets to your docs
5. **Mobile-friendly**: Test on mobile devices
6. **Fast loading**: Optimize images and minimize external dependencies
7. **SEO-friendly**: Add proper meta tags and structured data

## 🔄 Automation

### Auto-generate from Code

```yaml
# GitHub Action to generate OpenAPI from code
name: Generate API Docs
on:
  push:
    branches: [main]
    paths: ['src/**']

jobs:
  generate-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate OpenAPI
        run: |
          # Your code to generate openapi.yaml from source
          python scripts/generate-openapi.py > docs/openapi.yaml
      - name: Commit updated docs
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add docs/openapi.yaml
          git commit -m "Auto-update API documentation" || exit 0
          git push
```

Your documentation site will be professional, interactive, and automatically deployable! 🎉
