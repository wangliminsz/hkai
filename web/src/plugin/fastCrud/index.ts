import type { App } from 'vue';

let appRef: App | null = null;
let loadPromise: Promise<void> | null = null;

export function setFastCrudApp(app: App) {
	appRef = app;
}

export function ensureFastCrud(): Promise<void> {
	if (loadPromise) return loadPromise;
	if (!appRef) return Promise.resolve();
	loadPromise = import('/@/settings')
		.then(({ default: fastCrud }) => {
			appRef!.use(fastCrud);
		})
		.catch((err) => {
			loadPromise = null;
			throw err;
		});
	return loadPromise;
}
