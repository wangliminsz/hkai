import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import { directive } from '/@/directive/index';
import { i18n } from '/@/i18n';
import other from '/@/utils/other';
import '/@/assets/style/tailwind.css'; // 先引入tailwind css, 以免element-plus冲突
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import '/@/assets/fonts/poppins/poppins.css';
import '/@/theme/index.scss';
import mitt from 'mitt';
import VueGridLayout from 'vue-grid-layout';
import piniaPersist from 'pinia-plugin-persist';
import pinia from './stores';
import { setFastCrudApp } from '/@/plugin/fastCrud';
import 'font-awesome/css/font-awesome.min.css';
import '/@/assets/iconfont/iconfont.css'; //引入css
import '/@/assets/iconfont/iconfont-01/iconfont.css'; //引入css
import '/@/assets/iconfont/iconfont-02/iconfont.css'; //引入css
// 自动注册插件(已停用: 本站无 dvadmin npm 插件依赖, 避免扫描噪音; 需要时取消注释)
// import { scanAndInstallPlugins } from '/@/views/plugins/index';

import '/@/assets/style/reset.scss';
import 'element-tree-line/dist/style.css'

let app = createApp(App);
setFastCrudApp(app);

// scanAndInstallPlugins(app); // 已停用(见上方 import 注释)

pinia.use(piniaPersist);
directive(app);
other.elSvg(app);


app.use(pinia)
	.use(router)
	.use(ElementPlus, { i18n: i18n.global.t })
	.use(i18n)
	.use(VueGridLayout)
	.mount('#app');

app.config.globalProperties.mittBus = mitt();
