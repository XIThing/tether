import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./index.css";
import "diff2html/bundles/css/diff2html.min.css";
import ActiveSession from "./views/ActiveSession.vue";
import Settings from "./views/Settings.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: ActiveSession },
    { path: "/settings", component: Settings }
  ]
});

createApp(App).use(router).mount("#app");
