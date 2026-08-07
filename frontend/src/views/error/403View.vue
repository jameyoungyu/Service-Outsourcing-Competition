<template>
  <div class="error-page">
    <el-result icon="warning" title="403 拒绝访问" sub-title="无权访问当前区域">
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
