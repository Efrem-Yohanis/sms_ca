# Interface Essentials

create only ui for this

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://form-fun-folio.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/5728a561-f6f8-4b93-8750-147f3a82f0e8).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```

## Docker Compose

The root `compose.yaml` builds and runs this admin UI alongside the admin
backend and campaign UI. By default, the UI connects to
`http://localhost:8002/api/v1`; set `VITE_ADMIN_API_URL` to the browser-
reachable admin API URL when deploying elsewhere.
