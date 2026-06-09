#!/bin/bash
export PATH="/opt/homebrew/opt/node@20/bin:$PATH"
cd /Users/rishikavaish/Documents/Projects/infergate/dashboard
exec node_modules/.bin/next dev -p 3000
