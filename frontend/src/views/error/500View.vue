<template>
  <div class="error-page">
    <el-result icon="error" title="500 服务端异常" sub-title="后端服务异常，请重试就绪检查">
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
