<template>
  <div class="error-page">
    <el-result icon="error" title="404 页面未找到" sub-title="您访问的路径不存在或已被移走">
      <template #extra>
        <el-button type="primary" @click="$router.push('/')">返回工作台</el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.error-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80vh;
}
</style>
