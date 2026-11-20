import { createApp } from 'vue';
import Vant from 'vant';
import 'vant/lib/index.css';
import App from './App.vue';
import router from './router';
import pinia from './stores';
import './styles/global.css';

document.documentElement.classList.add('van-theme-dark');

createApp(App).use(pinia).use(router).use(Vant).mount('#app');
