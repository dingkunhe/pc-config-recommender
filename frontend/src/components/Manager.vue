<template>
  <div class="manager-page">
    <div class="tabs">
      <button v-if="isForumMode" :class="{active: activeTab === 'posts'}" @click="activeTab = 'posts'">恢复删帖 (30天内)</button>
      <button v-if="isForumMode" :class="{active: activeTab === 'users'}" @click="activeTab = 'users'">用户封禁管理</button>
      <button v-if="isForumMode" :class="{active: activeTab === 'reports'}" @click="activeTab = 'reports'">举报管理</button>
      <button v-if="isForumMode" :class="{active: activeTab === 'ai_ban'}" @click="activeTab = 'ai_ban'">AI封禁管理</button>

      <button v-if="isRecommendMode" :class="{active: activeTab === 'api'}" @click="activeTab = 'api'">API配置管理</button>
      <button v-if="isRecommendMode" :class="{active: activeTab === 'audit'}" @click="activeTab = 'audit'">审核系统</button>
      <button v-if="isRecommendMode" :class="{active: activeTab === 'crawler'}" @click="activeTab = 'crawler'">数据更新管理</button>
      <button v-if="isRecommendMode" :class="{active: activeTab === 'hardware'}" @click="activeTab = 'hardware'">硬件数据</button>
      <button v-if="isRecommendMode" :class="{active: activeTab === 'prompts'}" @click="activeTab = 'prompts'">提示词优化</button>
      <button v-if="isRecommendMode" :class="{active: activeTab === 'schemes'}" @click="activeTab = 'schemes'">推荐方案数据库</button>
      <button v-if="isRecommendMode" :class="{active: activeTab === 'weights'}" @click="activeTab = 'weights'">权重调整</button>
      </div>
    
    
    <div v-if="isForumMode && activeTab === 'reports'" class="tab-content">
      <div v-if="reports.length === 0" class="empty">暂无待处理的举报</div>
      <div v-for="r in reports" :key="r.id" class="post-item" style="display: flex; flex-direction: column;">
        <div style="margin-bottom: 8px;">
          <strong>类型:</strong> {{ r.type }} | <strong>举报人:</strong> {{ r.reporter }} | <strong>时间:</strong> {{ new Date(r.created_at).toLocaleString() }}
        </div>
        <div style="background: #f9f9f9; padding: 10px; border-radius: 4px; margin-bottom: 8px;">
          <strong>内容 / 作者 ({{ r.author }}):</strong><br/>
          {{ r.content }}
        </div>
        <div class="post-actions" style="justify-content: flex-end;">
          <button class="restore-btn" style="background-color: #ff9800; margin-right: 10px;" @click="handleReport(r.id, 'ignore')">忽略</button>
          <button class="del-btn" style="background-color: #f44336;" @click="handleReport(r.id, 'delete')">删除并处理</button>
        </div>
      </div>
    </div>

    <div v-if="isForumMode && activeTab === 'posts'" class="tab-content">
      <div v-if="deletedPosts.length === 0 && deletedComments.length === 0" class="empty">暂无30天内已删除的帖子或回复</div>

      <div v-if="deletedPosts.length > 0" style="margin-bottom: 16px; font-weight: 700; color: #3b4d6d;">已删除帖子</div>
      <div v-for="post in deletedPosts" :key="post.id" class="post-item">
        <div class="post-header">
          <strong>{{ post.title }}</strong>
          <span style="color: #999; font-size: 12px; margin-left: 10px;">作者: {{ post.author }} | 删除: {{ new Date(post.deleted_at).toLocaleString() }}</span>
        </div>
        <div class="post-actions">
          <button class="restore-btn" @click="restorePost(post.id)">恢复</button>
        </div>
      </div>

      <div v-if="deletedComments.length > 0" style="margin: 18px 0 12px; font-weight: 700; color: #3b4d6d;">已删除回复</div>
      <div v-for="comment in deletedComments" :key="`c-${comment.id}`" class="post-item" style="align-items: flex-start;">
        <div class="post-header" style="display:flex; flex-direction:column; gap:4px;">
          <strong>回复 #{{ comment.id }}（帖子 #{{ comment.post_id }}）</strong>
          <span style="color: #666; font-size: 13px;">{{ comment.content }}</span>
          <span style="color: #999; font-size: 12px;">作者: {{ comment.author }} | 删除: {{ new Date(comment.deleted_at).toLocaleString() }}</span>
        </div>
        <div class="post-actions">
          <button class="restore-btn" @click="restoreComment(comment.id)">恢复</button>
        </div>
      </div>
    </div>
    
    <div v-if="isForumMode && activeTab === 'users'" class="tab-content">
      <div v-if="users.length === 0" class="empty">暂无用户</div>
      <div v-for="user in users" :key="user.id" class="user-item">
        <div class="user-info">
          <span>昵称: {{ user.nickname }}</span>
          <span style="margin-left:15px; color:#666;">账号: {{ user.username }}</span>
          <span v-if="user.banned" style="margin-left:15px; color:red; font-weight:bold;">[已封禁]</span>
        </div>
        <div class="user-actions">
          <button v-if="user.banned" class="restore-btn" @click="toggleBan(user.id, 'unban')">解封</button>
          <button v-else class="delete-btn" @click="toggleBan(user.id, 'ban')">封禁</button>
        </div>
      </div>
    </div>

    <div v-if="isForumMode && activeTab === 'ai_ban'" class="tab-content">
      <div v-if="aiHiddenPosts.length === 0 && aiHiddenComments.length === 0" class="empty">暂无AI隐藏内容</div>

      <div v-if="aiHiddenPosts.length > 0" style="margin-bottom: 16px; font-weight: 700; color: #3b4d6d;">被AI隐藏的动态（只读）</div>
      <div v-for="post in aiHiddenPosts" :key="`ai-p-${post.id}`" class="post-item" style="align-items: flex-start;">
        <div class="post-header" style="display:flex; flex-direction:column; gap:4px;">
          <strong>动态 #{{ post.id }}</strong>
          <span style="color:#444;">标题：{{ post.title }}</span>
          <span style="color: #666; font-size: 13px; white-space: pre-wrap;">{{ post.content }}</span>
          <span style="color:#d46b08; font-size:12px;" v-if="post.reason">命中原因：{{ post.reason }}</span>
          <span style="color:#999; font-size:12px;">作者: {{ post.author }} | 隐藏: {{ post.flagged_at ? new Date(post.flagged_at).toLocaleString() : '-' }}</span>
        </div>
      </div>

      <div v-if="aiHiddenComments.length > 0" style="margin: 18px 0 12px; font-weight: 700; color: #3b4d6d;">被AI隐藏的评论（可恢复/删除）</div>
      <div v-for="comment in aiHiddenComments" :key="`ai-c-${comment.id}`" class="post-item" style="align-items: flex-start;">
        <div class="post-header" style="display:flex; flex-direction:column; gap:4px; width:100%;">
          <strong>评论 #{{ comment.id }}（帖子 #{{ comment.post_id }}）</strong>
          <span style="color: #666; font-size: 13px; white-space: pre-wrap;">{{ comment.content }}</span>
          <span style="color:#d46b08; font-size:12px;" v-if="comment.reason">命中原因：{{ comment.reason }}</span>
          <span style="color:#999; font-size:12px;">作者: {{ comment.author }} | 隐藏: {{ comment.flagged_at ? new Date(comment.flagged_at).toLocaleString() : '-' }}</span>
        </div>
        <div class="post-actions">
          <button class="restore-btn" @click="restoreAiComment(comment.id)">恢复</button>
          <button class="delete-btn" style="margin-left: 10px;" @click="deleteAiComment(comment.id)">删除</button>
        </div>
      </div>
    </div>

    <!-- API管理模块 -->
    <div v-if="isRecommendMode && activeTab === 'api'" class="tab-content">
      <div style="margin-bottom: 15px; text-align: right;">
        <button class="restore-btn" @click="openApiModal('add', null, 'recommend')">+ 添加API配置</button>
      </div>
      <div v-if="apiConfigs.length === 0" class="empty">暂无API配置，请添加主API和备用API</div>
      <div v-for="api in apiConfigs" :key="api.id" class="api-item">
        <div class="api-info">
          <strong>{{ api.name }}</strong>
          <span v-if="api.is_primary" class="tag primary-tag">主API</span>
          <span v-else class="tag backup-tag">备用API</span>
          <span v-if="!api.is_active" class="tag disabled-tag">已停</span>
          <div class="api-details">
            <div>模型名称: {{ api.model_name }}</div>
            <div>Base URL: {{ api.base_url }}</div>
          </div>
        </div>
        <div class="api-actions">
          <button class="test-btn" @click="testApiConfig(api, 'recommend')">测试</button>
          <button class="edit-btn" style="margin-left: 10px;" @click="openApiModal('edit', api, 'recommend')">编辑</button>
          <button class="delete-btn" style="margin-left: 10px;" @click="deleteApiConfig(api.id, 'recommend')">删除</button>
        </div>
      </div>
    </div>

    <!-- 审核系统API管理模块 -->
    <div v-if="isRecommendMode && activeTab === 'audit'" class="tab-content">
      <div style="margin-bottom: 15px; display:flex; justify-content: space-between; align-items:center; gap:10px; flex-wrap: wrap;">
        <div style="color:#60708d; font-size:13px;">配置一个主审核API和多个备用API。推荐生成后将先经过审核系统校验正确性。</div>
        <button class="restore-btn" @click="openApiModal('add', null, 'audit')">+ 添加审核API</button>
      </div>
      <div v-if="auditApiConfigs.length === 0" class="empty">暂无审核系统API配置，请添加主API和备用API</div>
      <div v-for="api in auditApiConfigs" :key="`audit-${api.id}`" class="api-item">
        <div class="api-info">
          <strong>{{ api.name }}</strong>
          <span v-if="api.is_primary" class="tag primary-tag">主API</span>
          <span v-else class="tag backup-tag">备用API</span>
          <span v-if="!api.is_active" class="tag disabled-tag">已停</span>
          <div class="api-details">
            <div>模型名称: {{ api.model_name }}</div>
            <div>Base URL: {{ api.base_url }}</div>
          </div>
        </div>
        <div class="api-actions">
          <button class="test-btn" @click="testApiConfig(api, 'audit')">测试</button>
          <button class="edit-btn" style="margin-left: 10px;" @click="openApiModal('edit', api, 'audit')">编辑</button>
          <button class="delete-btn" style="margin-left: 10px;" @click="deleteApiConfig(api.id, 'audit')">删除</button>
        </div>
      </div>
    </div>

    <!-- 爬虫数据更新管理模块 -->
    <div v-if="isRecommendMode && activeTab === 'crawler'" class="tab-content">
      <div v-if="!showCrawlerLogs">
        <div class="crawler-control-panel">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <h3>中关村在线 硬件数据更新 (合规版爬虫)</h3>
            <button class="restore-btn" @click="showCrawlerLogs = true; fetchHistoryLogs()">查看历史日志</button>
          </div>
          <p style="color:#666; font-size:14px;">
          此动作将严格遵守 <a href="https://www.zol.com.cn/robots.txt" target="_blank" style="color:#1890ff;">ZOL robots.txt</a> 规范：自动过滤带 '?' 的动态参数，强制 1~3 秒请求延迟，并开启大模型结构化清洗，默认使用【API配置管理】里设为主API的大模型。
        </p>

        <div style="margin-top: 15px; padding: 12px; background-color: #e6f4ff; border: 1px solid #91caff; border-radius: 4px; max-width: 600px;">
          <strong>💡 AI 数据清洗配置提示：</strong>
          <p style="margin: 5px 0 0 0; font-size: 13px; color: #333;">
            由于数据清洗需要大量并发请求进行信息提取分析，目前已与推荐系统后台共用同一个 AI。
          </p>
          <ul style="margin: 5px 0 0 0; font-size: 13px; color: #333; padding-left: 20px;">
            <li>请前往 <strong><a href="#" @click.prevent="activeTab = 'api'">API配置管理</a></strong> 添加并启用大模型。</li>
            <li>推荐添加 <strong>智谱的 GLM-4-Flash</strong> 模型（调用成本低且速度快）。<br>
              <strong>配置参数说明：</strong><br>
              - 【模型名称】：<code>glm-4-flash</code><br>
              - 【Base URL】：<code>https://open.bigmodel.cn/api/paas/v4/chat/completions</code><br>
              - 【API Key】：您在智谱 AI 平台获取的 Key（如 <code>7f83ad...</code>）
            </li>
          </ul>
        </div>
        
        <div style="margin-top: 20px; display: flex; align-items: center; gap: 15px;">
          <div style="display: flex; align-items: center; gap: 10px;">
            <label style="font-weight: bold; font-size: 14px; color: #333;">每一类硬件爬取数量:</label>
            <input 
              type="number" 
              v-model.number="itemsPerCategory" 
              min="1" 
              max="500" 
              class="items-input" 
              style="width: 80px; padding: 5px; border: 1px solid #ccc; border-radius: 4px;"
            />
          </div>
          <button
            class="restore-btn"
            style="padding: 10px 20px; font-size: 16px;"
            @click="startCrawler"
            :disabled="spiderStatus.is_running"
          >
            {{ spiderStatus.is_running ? '爬虫正在运行中...' : '▶ 启动数据更新任务' }}
          </button>
          
          <span v-if="spiderStatus.is_running" style="color: #52c41a; font-weight: bold;">
             爬虫已成功启动，正在后台运行...
          </span>
        </div>
        
        <div class="spider-status" style="margin-top: 25px; padding: 15px; background: #f5f5f5; border-radius:8px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <h4>实时状态监</h4>
            <button 
              v-if="spiderStatus.is_running"
              @click="stopCrawler" 
              style="padding: 5px 15px; background-color: #ff4d4f; color: white; border: none; border-radius: 4px; cursor: pointer;"
            >
               中断爬虫
            </button>
          </div>
          <p><strong>当前动作:</strong> <span style="color:#fa8c16;">{{ spiderStatus.current_task || '空闲' }}</span></p>
          <p><strong>已入库商品数:</strong> {{ spiderStatus.total_scraped || 0 }}</p>
          <div class="log-console">
            <div v-for="(log, idx) in spiderStatus.logs" :key="idx" class="log-line">{{ log }}</div>
            <div v-if="!spiderStatus.logs || spiderStatus.logs.length===0" style="color:#aaa;">暂无日志输出...</div>
          </div>
        </div>
      </div>
      </div>
      
      <!-- 历史日志展示 -->
      <div v-else>
        <div style="margin-bottom: 20px;">
          <button class="restore-btn" @click="showCrawlerLogs = false"><- 返回控制面板</button>
          <span style="font-size: 18px; font-weight: bold; margin-left: 15px;">历史日志记录</span>
          <button class="restore-btn" style="margin-left: 12px;" @click="exportCrawlerLogs()">导出全部日志</button>
        </div>
        <div v-if="historyLogs.length === 0" class="empty">暂无历史日志</div>
        <div v-else class="logs-container" style="display:flex; flex-direction:column; gap:15px;">
          <div v-for="log in historyLogs" :key="log.id" style="background: #f9f9f9; padding: 15px; border-radius: 8px; border: 1px solid #eee;">
            <div style="display:flex; justify-content: space-between; margin-bottom: 10px;">
              <strong>任务 ID: {{ log.id }}</strong>
              <div style="display:flex; gap:8px; align-items:center;">
                <span class="tag" :class="log.status === 'completed' ? 'primary-tag' : (log.status === 'running' ? 'backup-tag' : 'disabled-tag')">
                  {{ log.status === 'completed' ? '已完成' : (log.status === 'running' ? '运行中' : '已中断') }}
                </span>
                <button class="restore-btn" style="padding: 4px 10px;" @click="exportCrawlerLogs(log.id)">导出</button>
              </div>
            </div>
            <div style="font-size: 13px; color: #666; margin-bottom: 10px;">
              开始: {{ log.start_time }}<br>
              结束: {{ log.end_time || '-' }}
            </div>
            <textarea readonly style="width: 100%; height: 150px; background: #222; color: #0f0; border-radius: 4px; padding: 10px; font-family: monospace; font-size: 12px; border: none;">{{ log.log_text || '无日志输出' }}</textarea>
          </div>
        </div>
      </div>

    </div>

    <!-- 硬件数据管理 -->
    <div v-if="isRecommendMode && activeTab === 'hardware'" class="tab-content">
      <div style="margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;">
        <div style="display:flex; align-items:center; gap:8px;">
          <input ref="sqlFileInput" type="file" accept=".sql" style="display:none;" @change="onSqlFileSelected" />
          <button class="restore-btn" @click="$refs.sqlFileInput && $refs.sqlFileInput.click()" style="background:#5b8ff9; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;">
            📥 选择SQL文件
          </button>
          <span v-if="selectedSqlFile" style="font-size:12px; color:#666; max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{{ selectedSqlFile.name }}</span>
          <button class="restore-btn" :disabled="!selectedSqlFile || importingSql" @click="importHardwareSql" style="background:#13c2c2; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;">
            {{ importingSql ? '导入中...' : '⬆ 导入SQL' }}
          </button>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button
          class="restore-btn"
          @click="hardwareCorrectionMode = !hardwareCorrectionMode"
          :style="hardwareCorrectionMode ? 'background:#f59e0b; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;' : 'background:#6f56d9; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;'"
        >
          {{ hardwareCorrectionMode ? '✅ 退出纠错模式' : '✏ 进入纠错模式' }}
        </button>
        <button class="restore-btn" @click="transformHardwareData" style="background:#4c8bdc; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;" title="将原有硬件数据转换为新结构，自动补全品牌字段并规范化名称与型号">
          🔄 数据转换
        </button>
        <button
          class="restore-btn"
          @click="completeHardwareDescriptions"
          :disabled="hardwareCompleting"
          style="background:#722ed1; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;"
          title="调用推荐系统API补全当前筛选硬件数据的参数描述，重点补全适合场景"
        >
          {{ hardwareCompleting ? '补全中...' : '🧠 数据补全' }}
        </button>
        <button
          class="restore-btn"
          @click="vectorizeHardwareData"
          :disabled="hardwareVectorizing"
          style="background:#1d39c4; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;"
          title="将当前筛选硬件逐条向量化并写入向量数据库"
        >
          {{ hardwareVectorizing ? '向量化中...' : '🧩 向量化' }}
        </button>
        <button
          class="restore-btn"
          @click="cleanupOldVectorStore"
          :disabled="hardwareVectorCleaning"
          style="background:#8c8c8c; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;"
          title="清理旧版向量库（无维度后缀的旧集合/旧表），保留新版维度分库"
        >
          {{ hardwareVectorCleaning ? '清理中...' : '🗑 清理旧向量库' }}
        </button>
        <button class="restore-btn" @click="cleanupHardwareData" style="background:#ff4d4f; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;" title="由于爬虫可能抓取失败或有重复记录，点击此按钮清理价格为0或硬件名重复的数据">
          🧹 清理无效与重复数据
        </button>
        </div>
      </div>

      <div class="hardware-filter-panel">
        <div class="hardware-filter-row">
          <div class="hardware-filter-item">
            <label>类别</label>
            <select v-model="hardwareFilters.category" class="filter-input">
              <option value="">全部类别</option>
              <option v-for="c in hardwareFilterOptions.categories" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </div>

          <div class="hardware-filter-item">
            <label>品牌</label>
            <select v-model="hardwareFilters.brand" class="filter-input">
              <option value="">全部品牌</option>
              <option v-for="b in hardwareFilterOptions.brands" :key="b" :value="b">{{ b }}</option>
            </select>
          </div>

          <div class="hardware-filter-item">
            <label>最低价格(元)</label>
            <input v-model.number="hardwareFilters.minPrice" type="number" min="0" class="filter-input" placeholder="如 1000" />
          </div>

          <div class="hardware-filter-item">
            <label>最高价格(元)</label>
            <input v-model.number="hardwareFilters.maxPrice" type="number" min="0" class="filter-input" placeholder="如 5000" />
          </div>

          <div class="hardware-filter-item hardware-filter-item-keyword">
            <label>名称查询</label>
            <input
              v-model.trim="hardwareFilters.keyword"
              type="text"
              class="filter-input"
              placeholder="请输入硬件名称关键词"
              @keyup.enter="applyHardwareFilters"
            />
          </div>
        </div>

        <div class="hardware-filter-actions">
          <button class="restore-btn" @click="applyHardwareFilters">查询</button>
          <button class="cancel-btn" style="margin-left: 8px;" @click="resetHardwareFilters">重置</button>
          <span class="hardware-filter-total">筛选结果：{{ hardwareList.length }} 条</span>
        </div>
      </div>

      <div v-if="hardwareList.length === 0" class="empty">数据库暂无硬件数据记录。请使用数据更新功能后查看</div>
      <div v-else>
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>类别</th>
              <th>硬件名称</th>
              <th>品牌</th>
              <th>型号</th>
              <th>最新价格(元)</th>
              <th>参数描述</th>
              <th v-if="hardwareCorrectionMode">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="hw in hardwareList" :key="hw.id">
              <td>{{ hw.id }}</td>
              <td class="cell-ellipsis" :title="hw.category_label || hw.category">
                <template v-if="hardwareCorrectionMode">
                  <select v-model="hw.editForm.category" class="edit-input">
                    <option v-for="c in hardwareFilterOptions.categories" :key="`edit-cat-${c.value}`" :value="c.value">{{ c.label }}</option>
                  </select>
                </template>
                <template v-else>
                  {{ hw.category_label || hw.category || '其他' }}
                </template>
              </td>
              <td class="cell-ellipsis" :title="hw.name">
                <template v-if="hardwareCorrectionMode">
                  <input v-model="hw.editForm.name" class="edit-input" type="text" />
                </template>
                <template v-else>
                  {{ hw.name }}
                </template>
              </td>
              <td class="cell-ellipsis" :title="hw.brand">
                <template v-if="hardwareCorrectionMode">
                  <select v-model="hw.editForm.brand" class="edit-input">
                    <option value="">(空)</option>
                    <option v-for="b in getEditableBrandOptions(hw.editForm.brand)" :key="`edit-brand-${hw.id}-${b}`" :value="b">{{ b }}</option>
                  </select>
                </template>
                <template v-else>
                  {{ hw.brand || 'N/A' }}
                </template>
              </td>
              <td class="cell-ellipsis" :title="hw.model">
                <template v-if="hardwareCorrectionMode">
                  <input v-model="hw.editForm.model" class="edit-input" type="text" />
                </template>
                <template v-else>
                  {{ hw.model || 'N/A' }}
                </template>
              </td>
              <td style="color: #fa8c16; font-weight: bold;">
                <template v-if="hardwareCorrectionMode">
                  <input v-model="hw.editForm.price" class="edit-input" type="text" placeholder="如 3999" />
                </template>
                <template v-else>
                  <span v-if="hw.price_history && hw.price_history.length > 0">{{ hw.price_history[0].price }}</span>
                  <span v-else>无报价</span>
                </template>
              </td>
              <td style="max-width: 300px;">
                <div v-show="!hw.expanded" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; justify-content: space-between;">
                  <span style="overflow: hidden; text-overflow: ellipsis;">{{ hw.description }}</span>
                  <a href="#" @click.prevent="hw.expanded = true" style="color:#4c8bdc; font-size:12px; margin-left: 5px; flex-shrink: 0;">展开</a>
                </div>
                <div v-show="hw.expanded" style="white-space: normal; line-height: 1.5;">
                  {{ hw.description }}
                  <div style="text-align: right; margin-top: 5px;">
                    <a href="#" @click.prevent="hw.expanded = false" style="color:#4c8bdc; font-size:12px;">收起全部</a>
                  </div>
                </div>
              </td>
              <td v-if="hardwareCorrectionMode" style="white-space: nowrap;">
                <button class="restore-btn" @click="saveHardwareCorrection(hw)" :disabled="hardwareSavingId === hw.id" style="padding: 6px 10px;">
                  {{ hardwareSavingId === hw.id ? '保存中...' : '保存' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 提示词优化 -->
    <div v-if="isRecommendMode && activeTab === 'prompts'" class="tab-content">
      <div class="prompt-tip-box">
        <strong>使用说明：</strong>
        <ul>
          <li>推荐提示词支持占位符 <code v-pre>{{knowledge_str}}</code>，请勿删除。</li>
          <li>审核提示词建议只输出 JSON，避免额外说明文本。</li>
          <li>保存后将立即生效于新的推荐与审核请求。</li>
        </ul>
      </div>

      <div class="prompt-editor-group">
        <label class="prompt-label">推荐系统提示词</label>
        <textarea
          v-model="promptForm.recommend_prompt"
          class="prompt-textarea"
          rows="10"
          placeholder="请输入推荐系统提示词"
        ></textarea>
      </div>

      <div class="prompt-editor-group">
        <label class="prompt-label">审核系统提示词</label>
        <textarea
          v-model="promptForm.audit_prompt"
          class="prompt-textarea"
          rows="10"
          placeholder="请输入审核系统提示词"
        ></textarea>
      </div>

      <div class="prompt-editor-group" style="max-width: 420px;">
        <label class="prompt-label">按类别召回数量（TopK）</label>
        <input
          v-model.number="promptForm.rag_top_k_per_category"
          type="number"
          min="1"
          max="20"
          class="filter-input"
          placeholder="每个硬件类别召回条数，默认5"
        />
        <div style="margin-top:6px; color:#60708d; font-size:12px;">用于 RAG 阶段在每一类硬件向量库中的相似检索数量，建议范围 3~8。</div>
      </div>

      <div class="prompt-actions">
        <button class="restore-btn" :disabled="promptSaving" @click="savePromptConfigs">
          {{ promptSaving ? '保存中...' : '保存提示词' }}
        </button>
        <button class="test-btn" style="margin-left: 10px;" :disabled="promptLoading || promptSaving" @click="fetchPromptConfigs">
          {{ promptLoading ? '同步中...' : '刷新同步' }}
        </button>
        <button class="cancel-btn" style="margin-left: 10px;" :disabled="promptSaving" @click="resetPromptConfigs">恢复默认</button>
        <span v-if="promptLoading" style="margin-left: 12px; color: #60708d; font-size: 13px;">加载中...</span>
        <span v-else-if="promptUpdatedAt" style="margin-left: 12px; color: #60708d; font-size: 13px;">最近更新：{{ promptUpdatedAt }}</span>
      </div>
    </div>


    <!-- 推荐方案数据库 -->
    <div v-if="isRecommendMode && activeTab === 'schemes'" class="tab-content">
      <div style="margin-bottom: 15px; display: flex; justify-content: flex-end;">
        <button class="restore-btn" @click="triggerDailyClean" style="background:#4CAF50; border:none; padding:8px 15px; color:white; border-radius:4px; cursor:pointer;" title="手动立即执行每日清洗提取任务（需等待处理完成）">
           立即执行本地区清洗提取
        </button>
      </div>
      <div v-if="schemes.length === 0" class="empty">暂无精选推荐方案。每天23点会自动从高赞动态和评论中筛选提取。</div>
      <div v-else>
        <div v-for="sc in schemes" :key="sc.id" class="post-item" style="display: flex; flex-direction: column;">
          <div style="margin-bottom: 8px;">
            <strong>来源:</strong> {{ sc.source_type === 'post' ? '帖子' : '评论' }} (ԴID: {{ sc.source_id }}) | <strong>时间:</strong> {{ new Date(sc.created_at).toLocaleString() }}
          </div>
          <div style="background: #f9f9f9; padding: 10px; border-radius: 4px; margin-bottom: 8px; white-space: pre-wrap;">
            <strong>标题: {{ sc.title }}</strong><br/>
            {{ sc.content }}
          </div>
          <div class="post-actions" style="justify-content: flex-end;">
            <button class="del-btn" style="background-color: #f44336;" @click="deleteScheme(sc.id)">删除方案</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="isRecommendMode && activeTab === 'weights'" class="tab-content">
      <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;">
        <div style="color:#60708d; font-size:13px;">系统每日 23:00 自动分析当日新增动态/评论，提取硬件口碑并调整推荐权重。</div>
        <button class="restore-btn" @click="fetchWeightAdjustments">刷新记录</button>
      </div>

      <div style="margin-bottom: 14px; font-weight:700; color:#3b4d6d;">当前高权重硬件（Top 30）</div>
      <div v-if="weightHardware.length === 0" class="empty" style="margin: 10px 0 18px;">暂无权重数据</div>
      <table v-else class="data-table" style="margin-bottom: 18px;">
        <thead>
          <tr>
            <th>ID</th>
            <th>硬件</th>
            <th>品牌</th>
            <th>权重</th>
            <th>最近调整时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in weightHardware" :key="`w-h-${h.id}`">
            <td>{{ h.id }}</td>
            <td>{{ h.name }} <span v-if="h.model">({{ h.model }})</span></td>
            <td>{{ h.brand || 'N/A' }}</td>
            <td style="font-weight:700; color:#1677ff;">{{ Number(h.recommend_weight || 1).toFixed(3) }}</td>
            <td>{{ h.weight_updated_at ? new Date(h.weight_updated_at).toLocaleString() : '-' }}</td>
          </tr>
        </tbody>
      </table>

      <div style="margin-bottom: 10px; font-weight:700; color:#3b4d6d;">权重调整记录（最新）</div>
      <div v-if="weightLogs.length === 0" class="empty">暂无调整记录</div>
      <div v-for="log in weightLogs" :key="`wlog-${log.id}`" class="post-item" style="display:flex; flex-direction:column; align-items:flex-start;">
        <div style="margin-bottom: 6px;">
          <strong>{{ log.hardware_name }}</strong>
          <span v-if="log.hardware_model"> ({{ log.hardware_model }})</span>
          <span style="margin-left: 10px; color:#666;">来源: {{ log.source_type === 'post' ? '动态' : '评论' }} #{{ log.source_id }}</span>
        </div>
        <div style="font-size:13px; color:#555; margin-bottom:4px;">提及词: {{ log.mention_text || '-' }}</div>
        <div style="font-size:13px; margin-bottom:4px;">
          情感: <strong>{{ log.sentiment }}</strong>
          | 置信度: {{ Number(log.confidence || 0).toFixed(2) }}
          | 权重: {{ Number(log.weight_before || 1).toFixed(3) }} → {{ Number(log.weight_after || 1).toFixed(3) }}
          | 变化: <span :style="(log.delta || 0) >= 0 ? 'color:#16a34a;' : 'color:#dc2626;'">{{ (log.delta || 0) >= 0 ? '+' : '' }}{{ Number(log.delta || 0).toFixed(3) }}</span>
        </div>
        <div v-if="log.reason" style="font-size:13px; color:#666; margin-bottom:4px;">原因: {{ log.reason }}</div>
        <div style="font-size:12px; color:#999; margin-bottom:6px;">时间: {{ log.created_at }}</div>
        <div style="width:100%; background:#f9f9f9; border-radius:6px; padding:8px; color:#666; font-size:12px; white-space: pre-wrap;">{{ log.source_excerpt || '-' }}</div>
      </div>
    </div>

    <!-- API配置弹窗 -->

    <div v-if="showApiModal" class="modal-overlay">
      <div class="modal-content">
        <h3>{{ apiModalType === 'add' ? (apiModalScope === 'audit' ? '添加审核API配置' : '添加API配置') : (apiModalScope === 'audit' ? '编辑审核API配置' : '编辑API配置') }}</h3>
        <form @submit.prevent="saveApiConfig">
          <div class="form-group">
            <label>名称:</label>
            <input type="text" v-model="currentApi.name" required placeholder="如：硅基流动 主力节点">
          </div>
          <div class="form-group">
            <label>API Key:</label>
            <input type="text" v-model="currentApi.api_key" required placeholder="sk-...">
          </div>
          <div class="form-group">
            <label>模型名称:</label>
            <input type="text" v-model="currentApi.model_name" required placeholder="如：deepseek-ai/DeepSeek-V3">
          </div>
          <div class="form-group">
            <label>Base URL:</label>
            <input type="text" v-model="currentApi.base_url" required placeholder="https://api.siliconflow.cn/v1/chat/completions">
          </div>
          <div class="form-group checkbox-group">
            <label>
              <input type="checkbox" v-model="currentApi.is_primary"> 设置为主API (Ψһ)
            </label>
            <label style="margin-left: 20px;">
              <input type="checkbox" v-model="currentApi.is_active"> 启用该配置
            </label>
          </div>
          <div class="modal-actions">
            <button type="button" class="cancel-btn" @click="showApiModal = false">取消</button>
            <button type="submit" class="restore-btn">保存</button>
          </div>
        </form>
      </div>
    </div>

  </div>
</template>

<script>
import axios from 'axios'
export default {
  props: {
    mode: {
      type: String,
      default: 'forum'
    }
  },
  data() {
    return {
      activeTab: 'posts',
      reports: [],
      aiHiddenPosts: [],
      aiHiddenComments: [],
      schemes: [],
      deletedPosts: [],
      deletedComments: [],
      users: [],
      apiConfigs: [],
      auditApiConfigs: [],
      weightLogs: [],
      weightHardware: [],
      hardwareList: [],
      hardwareFilterOptions: {
        categories: [],
        brands: []
      },
      hardwareFilters: {
        category: '',
        brand: '',
        minPrice: '',
        maxPrice: '',
        keyword: ''
      },
      hardwareCorrectionMode: false,
      hardwareSavingId: null,
      hardwareCompleting: false,
      hardwareVectorizing: false,
      hardwareVectorCleaning: false,
      historyLogs: [],
      showCrawlerLogs: false,
      showApiModal: false,
      apiModalType: 'add',
      apiModalScope: 'recommend',
      currentApi: {},
      itemsPerCategory: 50,
      selectedSqlFile: null,
      importingSql: false,
      promptLoading: false,
      promptSaving: false,
      promptUpdatedAt: '',
      promptForm: {
        recommend_prompt: '',
        audit_prompt: '',
        rag_top_k_per_category: 5,
      },
      promptDefaults: {
        recommend_prompt: '',
        audit_prompt: '',
        rag_top_k_per_category: 5,
      },

      spiderStatus: {
        is_running: false,
        total_scraped: 0,
        current_task: '空闲',
        logs: []
      },
      pollingInterval: null
    }
  },
  computed: {
    isForumMode() {
      return this.mode !== 'recommend'
    },
    isRecommendMode() {
      return this.mode === 'recommend'
    }
  },
  mounted() {
    this.activeTab = this.isRecommendMode ? 'api' : 'posts';
    this.refreshByTab(this.activeTab);
    if (this.isRecommendMode) {
      this.pollSpiderStatus();
    }
  },
  watch: {
    activeTab(newTab) {
      this.refreshByTab(newTab);
    },
    mode() {
      this.activeTab = this.isRecommendMode ? 'api' : 'posts';
      this.refreshByTab(this.activeTab);
      if (this.isRecommendMode && !this.pollingInterval) {
        this.pollSpiderStatus();
      }
    }
  },
  beforeUnmount() {
    if (this.pollingInterval) clearInterval(this.pollingInterval);
  },
  methods: {
    refreshByTab(tab) {
      if (this.isForumMode) {
        if (tab === 'posts') this.fetchDeletedPosts();
        else if (tab === 'users') this.fetchUsers();
        else if (tab === 'reports') this.fetchReports();
        else if (tab === 'ai_ban') this.fetchAiBanList();
      } else {
        if (tab === 'api') this.fetchApiConfigs();
        else if (tab === 'audit') this.fetchAuditApiConfigs();
        else if (tab === 'crawler') {
          if (!this.pollingInterval) this.pollSpiderStatus();
          if (this.showCrawlerLogs) this.fetchHistoryLogs();
        }
        else if (tab === 'hardware') this.fetchHardwareList();
        else if (tab === 'prompts') this.fetchPromptConfigs();
        else if (tab === 'schemes') this.fetchSchemes();
        else if (tab === 'weights') this.fetchWeightAdjustments();
      }
    },
    async fetchPromptConfigs() {
      try {
        this.promptLoading = true;
        const res = await axios.get('/api/admin/prompt_configs/', { withCredentials: true });
        const data = res.data?.data || {};
        const defaults = res.data?.defaults || {};
        this.promptForm = {
          recommend_prompt: data.recommend_prompt || '',
          audit_prompt: data.audit_prompt || '',
          rag_top_k_per_category: Number(data.rag_top_k_per_category || 5),
        };
        this.promptDefaults = {
          recommend_prompt: defaults.recommend_prompt || '',
          audit_prompt: defaults.audit_prompt || '',
          rag_top_k_per_category: Number(defaults.rag_top_k_per_category || 5),
        };
        this.promptUpdatedAt = data.updated_at || '';
      } catch (e) {
        alert('获取提示词配置失败: ' + (e.response?.data?.error || e.message));
      } finally {
        this.promptLoading = false;
      }
    },
    async savePromptConfigs() {
      if (!this.promptForm.recommend_prompt || !this.promptForm.recommend_prompt.trim()) {
        alert('推荐系统提示词不能为空');
        return;
      }
      if (!this.promptForm.audit_prompt || !this.promptForm.audit_prompt.trim()) {
        alert('审核系统提示词不能为空');
        return;
      }
      const topk = Number(this.promptForm.rag_top_k_per_category);
      if (!Number.isInteger(topk) || topk < 1 || topk > 20) {
        alert('按类别召回数量（TopK）需为 1~20 的整数');
        return;
      }
      if (!this.promptForm.recommend_prompt.includes('{{knowledge_str}}')) {
        if (!confirm('推荐提示词中未包含 {{knowledge_str}} 占位符，可能导致知识检索内容无法注入。确定继续保存吗？')) {
          return;
        }
      }
      try {
        this.promptSaving = true;
        const payload = {
          action: 'save',
          recommend_prompt: this.promptForm.recommend_prompt,
          audit_prompt: this.promptForm.audit_prompt,
          rag_top_k_per_category: topk,
        };
        const res = await axios.post('/api/admin/prompt_configs/', payload, { withCredentials: true });
        alert(res.data?.message || '提示词保存成功');
        this.fetchPromptConfigs();
      } catch (e) {
        alert('保存提示词失败: ' + (e.response?.data?.error || e.message));
      } finally {
        this.promptSaving = false;
      }
    },
    async resetPromptConfigs() {
      if (!confirm('确定将推荐与审核提示词恢复为默认值吗？')) return;
      try {
        this.promptSaving = true;
        const res = await axios.post('/api/admin/prompt_configs/', { action: 'reset' }, { withCredentials: true });
        alert(res.data?.message || '已恢复默认提示词');
        this.fetchPromptConfigs();
      } catch (e) {
        alert('恢复默认失败: ' + (e.response?.data?.error || e.message));
      } finally {
        this.promptSaving = false;
      }
    },
    
    async fetchSchemes() {
      try {
        const res = await axios.get('/api/admin/schemes/', { withCredentials: true });
        this.schemes = res.data.data || [];
      } catch (err) {
        console.error('获取精华方案失败', err);
      }
    },
    async fetchWeightAdjustments() {
      try {
        const res = await axios.get('/api/admin/weight-adjustments/', { withCredentials: true });
        this.weightLogs = res.data.logs || [];
        this.weightHardware = res.data.hardware || [];
      } catch (err) {
        console.error('获取权重调整记录失败', err);
      }
    },
    async deleteScheme(id) {
      if(!confirm('确定要删除该推荐方案吗？')) return;
      try {
        await axios.post(`/api/admin/schemes/${id}/delete/`, {}, { withCredentials: true });
        alert('删除成功');
        this.fetchSchemes();
      } catch (err) {
        alert('删除失败: ' + (err.response?.data?.error || err.message));
      }
    },
    async triggerDailyClean() {
      if(!confirm('将立即启动数据分析任务去清洗论坛高赞内容，过程可能较长，确认执行？')) return;
      try {
        const res = await axios.post('/api/admin/trigger_daily_clean/', {}, { withCredentials: true });
        alert(res.data.message || '执行成功');
        this.fetchSchemes();
      } catch (err) {
        alert('执行失败: ' + (err.response?.data?.error || err.message));
      }
    },

    async fetchReports() {
      try {
        const res = await axios.get('/api/admin/reports/', { withCredentials: true });
        this.reports = res.data.reports || [];
      } catch (err) {
        console.error('获取举报列表失败', err);
      }
    },
    async fetchAiBanList() {
      try {
        const res = await axios.get('/api/admin/ai_ban/', { withCredentials: true });
        this.aiHiddenPosts = res.data.posts || [];
        this.aiHiddenComments = res.data.comments || [];
      } catch (err) {
        console.error('获取AI封禁列表失败', err);
      }
    },
    async restoreAiComment(commentId) {
      if (!confirm('确认恢复该评论并重新展示给用户？')) return;
      try {
        await axios.post(`/api/admin/ai_ban/comments/${commentId}/restore/`, {}, { withCredentials: true });
        alert('恢复成功');
        this.fetchAiBanList();
      } catch (err) {
        alert('恢复失败: ' + (err.response?.data?.error || err.message));
      }
    },
    async deleteAiComment(commentId) {
      if (!confirm('确认删除该评论？删除后将不再展示。')) return;
      try {
        await axios.post(`/api/admin/ai_ban/comments/${commentId}/delete/`, {}, { withCredentials: true });
        alert('删除成功');
        this.fetchAiBanList();
      } catch (err) {
        alert('删除失败: ' + (err.response?.data?.error || err.message));
      }
    },
    async handleReport(reportId, action) {
      if(!confirm(`确定要${action === 'delete' ? '删除该内容' : '忽略此举报'}吗？`)) return;
      try {
        const res = await axios.post(`/api/admin/reports/${reportId}/handle/`, { action }, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert('处理成功');
          this.fetchReports();
        }
      } catch (err) {
        alert('处理失败: ' + (err.response?.data?.error || err.message));
      }
    },
    async cleanupHardwareData() {
      if(!confirm('确定要清理掉数据库里价格为0以及除最新一条外的同名重复硬件数据吗？此操作不可逆！')) return;
      try {
        const res = await axios.post('http://localhost:8000/api/admin/hardware/cleanup/', {}, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert('清理完成: ' + res.data.message);
          this.fetchHardwareList();
        }
      } catch (err) {
        alert('清理失败: ' + (err.response?.data?.error || err.message));
      }
    },
    onSqlFileSelected(e) {
      const files = e?.target?.files || []
      const file = files[0]
      if (!file) return
      if (!file.name.toLowerCase().endsWith('.sql')) {
        alert('请选择 .sql 文件')
        e.target.value = ''
        this.selectedSqlFile = null
        return
      }
      this.selectedSqlFile = file
    },
    async importHardwareSql() {
      if (!this.selectedSqlFile) {
        alert('请先选择 SQL 文件')
        return
      }
      if (!confirm(`确认导入 SQL 文件：${this.selectedSqlFile.name} ？\n建议先备份数据库。`)) return
      try {
        this.importingSql = true
        const fd = new FormData()
        fd.append('file', this.selectedSqlFile)
        const res = await axios.post('/api/admin/hardware/import_sql/', fd, { withCredentials: true })
        alert(res.data.message || '导入成功')
        this.selectedSqlFile = null
        if (this.$refs.sqlFileInput) this.$refs.sqlFileInput.value = ''
        this.fetchHardwareList()
      } catch (err) {
        alert('导入失败: ' + (err.response?.data?.error || err.message))
      } finally {
        this.importingSql = false
      }
    },
    async transformHardwareData() {
      if(!confirm('将根据当前规则对硬件数据执行格式转换（补全品牌字段、规范名称/型号），确认执行？')) return;
      try {
        const res = await axios.post('/api/admin/hardware/transform/', {}, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert(res.data.message || '数据转换完成');
          this.fetchHardwareList();
        }
      } catch (err) {
        alert('数据转换失败: ' + (err.response?.data?.error || err.message));
      }
    },
    async completeHardwareDescriptions() {
      if (!this.hardwareList || this.hardwareList.length === 0) {
        alert('当前没有可补全的数据，请先查询硬件列表');
        return;
      }

      const ids = this.hardwareList.map(h => h.id).filter(Boolean);
      if (ids.length === 0) {
        alert('未获取到有效硬件ID');
        return;
      }

      if (!confirm(`将调用推荐系统API补全当前筛选结果（共 ${ids.length} 条）的参数描述，重点补全“适合场景”，确认执行？`)) return;

      try {
        this.hardwareCompleting = true;
        const res = await axios.post('/api/admin/hardware/complete_descriptions/', { ids }, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert(res.data.message || '数据补全完成');
          this.fetchHardwareList();
        }
      } catch (err) {
        alert('数据补全失败: ' + (err.response?.data?.error || err.message));
      } finally {
        this.hardwareCompleting = false;
      }
    },
    async vectorizeHardwareData() {
      if (!this.hardwareList || this.hardwareList.length === 0) {
        alert('当前没有可向量化的数据，请先查询硬件列表');
        return;
      }

      const ids = this.hardwareList.map(h => h.id).filter(Boolean);
      if (ids.length === 0) {
        alert('未获取到有效硬件ID');
        return;
      }

      if (!confirm(`将对当前筛选结果（共 ${ids.length} 条）逐条向量化并写入向量数据库，确认执行？`)) return;

      try {
        this.hardwareVectorizing = true;
        const res = await axios.post('/api/admin/hardware/vectorize/', { ids }, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert(res.data.message || '向量化完成');
        }
      } catch (err) {
        alert('向量化失败: ' + (err.response?.data?.error || err.message));
      } finally {
        this.hardwareVectorizing = false;
      }
    },
    async cleanupOldVectorStore() {
      if (!confirm('将删除旧版向量库（不带维度后缀的旧集合/旧表），此操作不可逆，确认继续？')) return;
      try {
        this.hardwareVectorCleaning = true;
        const res = await axios.post('/api/admin/hardware/vector_cleanup_old/', {}, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert(res.data.message || '旧向量库清理完成');
        }
      } catch (err) {
        alert('清理旧向量库失败: ' + (err.response?.data?.error || err.message));
      } finally {
        this.hardwareVectorCleaning = false;
      }
    },
    async fetchHardwareList() {
      try {
        const params = {};
        if (this.hardwareFilters.category) params.category = this.hardwareFilters.category;
        if (this.hardwareFilters.brand) params.brand = this.hardwareFilters.brand;
        if (this.hardwareFilters.minPrice !== '' && this.hardwareFilters.minPrice !== null && this.hardwareFilters.minPrice !== undefined) {
          params.min_price = this.hardwareFilters.minPrice;
        }
        if (this.hardwareFilters.maxPrice !== '' && this.hardwareFilters.maxPrice !== null && this.hardwareFilters.maxPrice !== undefined) {
          params.max_price = this.hardwareFilters.maxPrice;
        }
        if (this.hardwareFilters.keyword) params.keyword = this.hardwareFilters.keyword;

        const res = await axios.get('/api/admin/hardware/', { withCredentials: true, params });
        if (res.data.status === 'ok' || res.data.success) {
          this.hardwareList = res.data.data.map(hw => ({
            ...hw,
            expanded: false,
            editForm: {
              category: hw.category || 'other',
              name: hw.name || '',
              brand: hw.brand || '',
              model: hw.model || '',
              price: (hw.latest_price !== null && hw.latest_price !== undefined) ? String(hw.latest_price) : ''
            }
          }));
          if (res.data.filters) {
            this.hardwareFilterOptions.categories = res.data.filters.categories || [];
            this.hardwareFilterOptions.brands = res.data.filters.brands || [];
          }
        }
      } catch (err) {
        console.error('获取硬件数据失败', err);
      }
    },
    getEditableBrandOptions(currentBrand = '') {
      const set = new Set(this.hardwareFilterOptions.brands || []);
      const current = (currentBrand || '').trim();
      if (current) set.add(current);
      return Array.from(set).sort((a, b) => String(a).localeCompare(String(b), 'zh-CN'));
    },
    async saveHardwareCorrection(hw) {
      if (!hw || !hw.editForm) return;
      if (!hw.editForm.name || !String(hw.editForm.name).trim()) {
        alert('名称不能为空');
        return;
      }
      this.hardwareSavingId = hw.id;
      try {
        const payload = {
          id: hw.id,
          category: hw.editForm.category,
          name: hw.editForm.name,
          brand: hw.editForm.brand,
          model: hw.editForm.model,
          price: hw.editForm.price,
        };
        const res = await axios.post('/api/admin/hardware/update/', payload, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          const updated = res.data.data || {};
          hw.category = updated.category || hw.editForm.category;
          const categoryOpt = (this.hardwareFilterOptions.categories || []).find(c => c.value === hw.category);
          hw.category_label = categoryOpt ? categoryOpt.label : hw.category;
          hw.name = updated.name || hw.editForm.name;
          hw.brand = updated.brand !== undefined ? updated.brand : hw.editForm.brand;
          hw.model = updated.model !== undefined ? updated.model : hw.editForm.model;
          const latest = updated.latest_price;
          hw.latest_price = latest;
          hw.editForm.price = (latest !== null && latest !== undefined) ? String(latest) : '';
          hw.price_history = [{ date: new Date().toISOString().slice(0, 10), price: latest }];

          const b = (hw.brand || '').trim();
          if (b && !(this.hardwareFilterOptions.brands || []).includes(b)) {
            this.hardwareFilterOptions.brands = [...this.hardwareFilterOptions.brands, b].sort((a, z) => String(a).localeCompare(String(z), 'zh-CN'));
          }
        }
      } catch (err) {
        alert('保存失败: ' + (err.response?.data?.error || err.message));
      } finally {
        this.hardwareSavingId = null;
      }
    },
    applyHardwareFilters() {
      if (
        this.hardwareFilters.minPrice !== '' &&
        this.hardwareFilters.maxPrice !== '' &&
        Number(this.hardwareFilters.minPrice) > Number(this.hardwareFilters.maxPrice)
      ) {
        alert('价格区间不合法：最低价格不能大于最高价格');
        return;
      }
      this.fetchHardwareList();
    },
    resetHardwareFilters() {
      this.hardwareFilters = {
        category: '',
        brand: '',
        minPrice: '',
        maxPrice: '',
        keyword: ''
      };
      this.fetchHardwareList();
    },
    async fetchDeletedPosts() {
      try {
        const res = await axios.get('/api/admin/posts/deleted/', { withCredentials: true });
        this.deletedPosts = res.data.posts || [];
        this.deletedComments = res.data.comments || [];
      } catch (e) {
        console.error('Failed to fetch deleted posts', e);
      }
    },
    async fetchUsers() {
      try {
        const res = await axios.get('/api/admin/users/', { withCredentials: true });
        this.users = res.data.users || [];
      } catch (e) {
        console.error('Failed to fetch users', e);
      }
    },
    async fetchApiConfigs() {
      try {
        const res = await axios.get('/api/admin/api_configs/', { withCredentials: true });
        this.apiConfigs = res.data.configs || [];
      } catch (e) {
        console.error('Failed to fetch API configs', e);
      }
    },
    async fetchAuditApiConfigs() {
      try {
        const res = await axios.get('/api/admin/audit_api_configs/', { withCredentials: true });
        this.auditApiConfigs = res.data.configs || [];
      } catch (e) {
        console.error('Failed to fetch audit API configs', e);
      }
    },
    async testApiConfig(api, scope = 'recommend') {
      try {
        alert(`正在测试 ${api.name}，请稍候...`);
        const payload = {
          action: 'test',
          api_key: api.api_key,
          model_name: api.model_name,
          base_url: api.base_url
        };
        const endpoint = scope === 'audit' ? '/api/admin/audit_api_configs/' : '/api/admin/api_configs/'
        const res = await axios.post(endpoint, payload, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert(`测试成功！\n模型连通正常\n响应延迟: ${res.data.latency} ms`);
        }
      } catch (e) {
        alert('测试失败: ' + (e.response?.data?.error || e.message));
      }
    },
    async startCrawler() {

      try {
        const payload = { items_per_category: this.itemsPerCategory || 50 };
        const res = await axios.post('/api/admin/data_update/start/', payload, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          // 移除 alert 弹窗，状态将通过 template 中的 v-if 指示语隐式表达
          this.spiderStatus.is_running = true;
          if (!this.pollingInterval) {
            this.pollSpiderStatus();
          }
        }
      } catch (e) {
        alert('启动爬虫失败: ' + (e.response?.data?.error || e.message));
      }
    },
    async fetchHistoryLogs() {
      try {
        const res = await axios.get('/api/admin/scraper-logs/', { withCredentials: true });
        this.historyLogs = res.data.logs || [];
      } catch (err) {
        console.error('获取历史日志失败', err);
      }
    },
    async exportCrawlerLogs(logId = null) {
      try {
        const url = logId ? `/api/admin/scraper-logs/export/?id=${logId}` : '/api/admin/scraper-logs/export/';
        const res = await axios.get(url, { withCredentials: true, responseType: 'blob' });

        let filename = logId ? `scraper_log_${logId}.txt` : 'scraper_logs.txt';
        const disposition = res.headers['content-disposition'];
        if (disposition) {
          const match = disposition.match(/filename="?([^\"]+)"?/);
          if (match && match[1]) filename = decodeURIComponent(match[1]);
        }

        const blob = new Blob([res.data], { type: 'text/plain;charset=utf-8' });
        const link = document.createElement('a');
        const objectUrl = window.URL.createObjectURL(blob);
        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(objectUrl);
      } catch (err) {
        alert('导出失败: ' + (err.response?.data?.error || err.message));
      }
    },
    async stopCrawler() {
      if (!confirm('确定要中断当前正在运行的爬虫吗？(可能需要等待当前页面抓取完毕才会完全停止')) return;
      
      try {
        const res = await axios.post('/api/admin/data_update/stop/', {}, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
           // 不使用 alert，由状态面板自动更新"已发送中断指令" 日志
           // 由于并不是立即结束，在此不直接把 is_running 设为 false，而是等待轮询获取正确的 false ״̬
        }
      } catch (e) {
        alert('中断请求失败: ' + (e.response?.data?.error || e.message));
      }
    },
    pollSpiderStatus() {
      // 2秒轮询一次后台的抓取进度
      this.pollingInterval = setInterval(async () => {
        if (this.activeTab !== 'crawler' && !this.spiderStatus.is_running) return;
        try {
          const res = await axios.get('/api/admin/data_update/status/', { withCredentials: true });
          if (res.data.status === 'ok' || res.data.success) {
             this.spiderStatus = res.data.data;
          }
        } catch (e) {
          console.error("轮询爬虫状态失败", e);
        }
      }, 2000);
    },
    async restorePost(postId) {
      if(!confirm('确认恢复该帖子？')) return;
      try {
        await axios.post(`/api/admin/posts/${postId}/restore/`, {}, { withCredentials: true });
        alert('恢复成功');
        this.fetchDeletedPosts();
      } catch (e) {
        alert('恢复失败: ' + (e.response?.data?.error || e.message));
      }
    },
    async restoreComment(commentId) {
      if(!confirm('确认恢复该回复？')) return;
      try {
        await axios.post(`/api/admin/comments/${commentId}/restore/`, {}, { withCredentials: true });
        alert('恢复成功');
        this.fetchDeletedPosts();
      } catch (e) {
        alert('恢复失败: ' + (e.response?.data?.error || e.message));
      }
    },
    async toggleBan(userId, action) {
      if(!confirm(`确认${action==='ban'?'封禁':'解封'}该用户？`)) return;
      try {
        await axios.post(`/api/admin/users/${userId}/ban/`, { action }, { withCredentials: true });
        alert(`${action==='ban'?'封禁':'解封'}成功`);
        this.fetchUsers();
      } catch (e) {
        alert(`操作失败: ` + (e.response?.data?.error || e.message));
      }
    },
    openApiModal(type, api = null, scope = 'recommend') {
      this.apiModalType = type;
      this.apiModalScope = scope;
      if (type === 'add') {
        this.currentApi = {
          name: '',
          api_key: '',
          model_name: '',
          base_url: 'https://api.siliconflow.cn/v1/chat/completions',
          is_primary: false,
          is_active: true
        };
      } else {
        this.currentApi = { ...api };
      }
      this.showApiModal = true;
    },
    async saveApiConfig() {
      try {
        const payload = { ...this.currentApi, action: this.apiModalType };
        const endpoint = this.apiModalScope === 'audit' ? '/api/admin/audit_api_configs/' : '/api/admin/api_configs/'
        await axios.post(endpoint, payload, { withCredentials: true });
        alert('保存成功');
        this.showApiModal = false;
        if (this.apiModalScope === 'audit') this.fetchAuditApiConfigs();
        else this.fetchApiConfigs();
      } catch (e) {
        alert('保存失败: ' + (e.response?.data?.error || e.message));
      }
    },
    async deleteApiConfig(id, scope = 'recommend') {
      if(!confirm('确认删除该API配置？')) return;
      try {
        const endpoint = scope === 'audit' ? '/api/admin/audit_api_configs/' : '/api/admin/api_configs/'
        await axios.post(endpoint, { action: 'delete', id }, { withCredentials: true });
        alert('删除成功');
        if (scope === 'audit') this.fetchAuditApiConfigs();
        else this.fetchApiConfigs();
      } catch (e) {
        alert('删除失败: ' + (e.response?.data?.error || e.message));
      }
    },
    async testApiConfig(api, scope = 'recommend') {
      try {
        alert(`正在测试 ${api.name}，请稍候...`);
        const payload = {
          action: 'test',
          api_key: api.api_key,
          model_name: api.model_name,
          base_url: api.base_url
        };
        const endpoint = scope === 'audit' ? '/api/admin/audit_api_configs/' : '/api/admin/api_configs/'
        const res = await axios.post(endpoint, payload, { withCredentials: true });
        if (res.data.status === 'ok' || res.data.success) {
          alert(`测试成功！\n模型连通正常\n响应延迟: ${res.data.latency} ms`);
        }
      } catch (e) {
        alert('测试失败: ' + (e.response?.data?.error || e.message));
      }
    }
  }
}
</script>

<style scoped>
.manager-page { padding: 20px; background: rgba(255,255,255,.96); border-radius: 16px; border: 1px solid #e7edf8; box-shadow: 0 12px 30px rgba(82,99,130,.1); position: relative; }
.tabs { margin-bottom: 20px; border-bottom: 1px solid #e7edf8; display: flex; gap: 10px; flex-wrap: wrap; padding-bottom: 8px; }
.tabs button { padding: 9px 14px; border: 1px solid transparent; background: #f7f9fe; cursor: pointer; font-size: 14px; color: #3b4d6d; border-radius: 10px; transition: .2s ease; }
.tabs button.active { color: #315ebf; border-color: #d8e4ff; background: #edf3ff; font-weight: 700; }
.empty { text-align: center; color: #8b97ae; margin-top: 30px; }
.tab-content { background: #fff; border: 1px solid #edf1f8; border-radius: 14px; padding: 14px; }
.post-item, .user-item, .api-item { display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px dashed #e8edf7; }
.post-item:last-child, .user-item:last-child, .api-item:last-child { border-bottom: none; }
.restore-btn { background: linear-gradient(135deg,#4c8bdc,#3b74d1); color: white; border: none; padding: 7px 12px; border-radius: 9px; cursor: pointer; }
.delete-btn { background: #f24f4f; color: white; border: none; padding: 7px 12px; border-radius: 9px; cursor: pointer; }
.edit-btn { background: #39b464; color: white; border: none; padding: 7px 12px; border-radius: 9px; cursor: pointer; }
.test-btn { background: #337eed; color: white; border: none; padding: 7px 12px; border-radius: 9px; cursor: pointer; }
.restore-btn:hover,.delete-btn:hover,.edit-btn:hover,.test-btn:hover { filter: brightness(.95); }
.api-details { margin-top: 8px; color: #64728d; font-size: 13px; }
.tag { font-size: 12px; padding: 3px 8px; border-radius: 999px; margin-left: 10px; color: white; }
.primary-tag { background-color: #f5222d; }
.backup-tag { background-color: #fa8c16; }
.disabled-tag { background-color: #d9d9d9; color: #333; }
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(30,38,55,0.45); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-content { background: white; padding: 24px; border-radius: 14px; width: 480px; border: 1px solid #e8edf7; box-shadow: 0 18px 42px rgba(46,61,89,.2); }
.modal-content h3 { margin-top: 0; margin-bottom: 20px; }
.form-group { margin-bottom: 15px; }
.form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
.form-group input[type="text"] { width: 100%; padding: 9px 12px; border: 1px solid #d8e1f3; border-radius: 10px; box-sizing: border-box; }
.checkbox-group label { display: inline-flex; align-items: center; font-weight: normal; }
.modal-actions { margin-top: 25px; text-align: right; }
.cancel-btn { background: #f2f5fb; border: 1px solid #e3e9f6; padding: 7px 12px; border-radius: 9px; cursor: pointer; margin-right: 10px; }
.cancel-btn:hover { background: #e9effa; }

.crawler-control-panel { padding: 10px; }
.log-console { margin-top: 10px; background: #111827; color: #92ffb8; font-family: monospace; font-size: 13px; height: 250px; overflow-y: auto; padding: 10px; border-radius: 8px; }
.log-line { margin-bottom: 4px; border-bottom: 1px solid #1f2937; padding-bottom: 2px; }

.data-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
.hardware-filter-panel {
  margin: 0 0 14px;
  padding: 12px;
  border: 1px solid #edf1f8;
  border-radius: 10px;
  background: #fafcff;
}
.hardware-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.hardware-filter-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 150px;
}
.hardware-filter-item-keyword {
  flex: 1;
  min-width: 220px;
}
.hardware-filter-item label {
  font-size: 12px;
  color: #5b6781;
}
.filter-input {
  height: 34px;
  border: 1px solid #d8e1f3;
  border-radius: 8px;
  padding: 0 10px;
  box-sizing: border-box;
  background: #fff;
}
.hardware-filter-actions {
  margin-top: 10px;
  display: flex;
  align-items: center;
}
.hardware-filter-total {
  margin-left: 12px;
  font-size: 13px;
  color: #60708d;
}
.edit-input {
  width: 100%;
  height: 32px;
  border: 1px solid #d8e1f3;
  border-radius: 6px;
  padding: 0 8px;
  box-sizing: border-box;
  font-size: 12px;
}
.data-table th,
.data-table td {
  border-bottom: 1px solid #edf1f8;
  padding: 10px;
  text-align: left;
  vertical-align: top;
}
.data-table th:nth-child(1), .data-table td:nth-child(1) { width: 70px; }
.data-table th:nth-child(2), .data-table td:nth-child(2) { width: 110px; }
.data-table th:nth-child(3), .data-table td:nth-child(3) { width: 210px; }
.data-table th:nth-child(4), .data-table td:nth-child(4) { width: 120px; }
.data-table th:nth-child(5), .data-table td:nth-child(5) { width: 220px; }
.data-table th:nth-child(6), .data-table td:nth-child(6) { width: 120px; }
.cell-ellipsis {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.prompt-tip-box {
  margin-bottom: 14px;
  border: 1px solid #dbe7ff;
  background: #f6f9ff;
  border-radius: 10px;
  padding: 10px 12px;
  color: #415171;
  font-size: 13px;
}
.prompt-tip-box ul {
  margin: 6px 0 0;
  padding-left: 18px;
}
.prompt-editor-group {
  margin-bottom: 12px;
}
.prompt-label {
  display: block;
  margin-bottom: 6px;
  color: #3b4d6d;
  font-weight: 700;
}
.prompt-textarea {
  width: 100%;
  border: 1px solid #d8e1f3;
  border-radius: 10px;
  padding: 10px;
  box-sizing: border-box;
  font-size: 13px;
  line-height: 1.6;
  font-family: "Consolas", "Monaco", "Courier New", monospace;
  resize: vertical;
  min-height: 180px;
}
.prompt-actions {
  display: flex;
  align-items: center;
}
</style>
