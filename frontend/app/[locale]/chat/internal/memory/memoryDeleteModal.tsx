import React from "react"
import { Modal } from "antd"
import { WarningFilled } from "@ant-design/icons"
import { useTranslation, Trans } from "react-i18next"

interface MemoryDeleteModalProps {
  visible: boolean
  targetTitle?: string | null
  onOk: () => void
  onCancel: () => void
}

/**
 * 承载“清空记忆”二次确认弹窗，仅负责 UI 展示。
 * 上层组件负责控制 visible 及回调逻辑。
 */
const MemoryDeleteModal: React.FC<MemoryDeleteModalProps> = ({ visible, targetTitle, onOk, onCancel }) => {
  const { t } = useTranslation()
  return (
    <Modal
      open={visible}
      title={
        <div className="flex items-center gap-2 text-lg font-bold">
          <span>{t('memoryDeleteModal.title')}</span>
        </div>
      }
      onOk={onOk}
      onCancel={onCancel}
      okText={t('memoryDeleteModal.clear')}
      cancelText={t('common.cancel')}
      okButtonProps={{ danger: true }}
      destroyOnClose
    >
      <div className="flex items-start gap-3 mt-4">
        <WarningFilled className="text-yellow-500 mt-1 mr-2" style={{ fontSize: "48px" }} />
        <div className="space-y-2">
          <p>
            <Trans i18nKey="memoryDeleteModal.description" values={{ title: targetTitle || '' }} components={{ strong: <strong /> }} />
          </p>
          <p className="text-gray-500 text-sm">{t('memoryDeleteModal.prompt')}</p>
        </div>
      </div>
    </Modal>
  )
}

export default MemoryDeleteModal

