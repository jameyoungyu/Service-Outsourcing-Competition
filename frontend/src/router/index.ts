import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import DefaultLayout from "../layouts/DefaultLayout.vue";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    component: DefaultLayout,
    redirect: "/dashboard",
    children: [
      {
        path: "dashboard",
        name: "Dashboard",
        component: () => import("../views/DashboardView.vue"),
        meta: { title: "工作台概览" },
      },
      {
        path: "simulation",
        name: "Simulation",
        component: () => import("../views/SimulationView.vue"),
        meta: { title: "仿真生成器" },
      },
      {
        path: "datasets",
        name: "Datasets",
        component: () => import("../views/DatasetsView.vue"),
        meta: { title: "数据资产 Hub" },
      },
      {
        path: "datasets/:id",
        name: "DatasetDetail",
        component: () => import("../views/DatasetDetailView.vue"),
        meta: { title: "数据集详情" },
      },
      {
        path: "preprocessing/cleaning",
        name: "Cleaning",
        component: () => import("../views/CleaningView.vue"),
        meta: { title: "时间规整与清洗" },
      },
      {
        path: "preprocessing/segmentation",
        name: "Segmentation",
        component: () => import("../views/SegmentationView.vue"),
        meta: { title: "动态响应区间优选" },
      },
      {
        path: "preprocessing/delay",
        name: "Delay",
        component: () => import("../views/DelayView.vue"),
        meta: { title: "多变量时滞分析" },
      },
      {
        path: "preprocessing/collinearity",
        name: "Collinearity",
        component: () => import("../views/CollinearityView.vue"),
        meta: { title: "共线性与变量筛选" },
      },
      {
        path: "modeling/arx",
        name: "ARXModeling",
        component: () => import("../views/ARXModelingView.vue"),
        meta: { title: "ARX 系统辨识" },
      },
      {
        path: "modeling/optimization",
        name: "OptunaOptimization",
        component: () => import("../views/OptunaView.vue"),
        meta: { title: "Optuna 闭环寻优" },
      },
      {
        path: "copilot",
        name: "Copilot",
        component: () => import("../views/CopilotView.vue"),
        meta: { title: "Agent 工作台" },
      },
      {
        path: "deliverables",
        name: "Deliverables",
        component: () => import("../views/DeliverablesView.vue"),
        meta: { title: "报告与交付中心" },
      },
      {
        path: "settings",
        name: "Settings",
        component: () => import("../views/SettingsView.vue"),
        meta: { title: "系统配置" },
      },
    ],
  },
  {
    path: "/403",
    name: "403",
    component: () => import("../views/error/403View.vue"),
  },
  {
    path: "/404",
    name: "404",
    component: () => import("../views/error/404View.vue"),
  },
  {
    path: "/500",
    name: "500",
    component: () => import("../views/error/500View.vue"),
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/404",
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - IndusOpt` : "IndusOpt 工模智优";
  next();
});

export default router;
