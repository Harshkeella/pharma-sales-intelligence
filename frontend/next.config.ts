import type { NextConfig } from 'next';
const config: NextConfig = { async rewrites(){return [{source:'/api/:path*',destination:`${process.env.BACKEND_URL||'http://127.0.0.1:8000'}/api/:path*`}];}, experimental:{proxyTimeout:300000,middlewareClientMaxBodySize:'110mb'}, serverExternalPackages:['@sparticuz/chromium','playwright-core','pptxgenjs'] };
export default config;
