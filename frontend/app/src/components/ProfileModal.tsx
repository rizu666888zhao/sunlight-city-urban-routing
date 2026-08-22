'use client'

interface Props {
  open: boolean
  onClose: () => void
  email: string
  onLogout: () => void
}

export default function ProfileModal({ open, onClose, email, onLogout }: Props) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-gray-900 rounded-lg p-6 w-[420px] max-w-[95%] border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">Profile</h3>
        <div className="mb-4">
          <p className="text-sm text-gray-400">Signed in as</p>
          <p className="text-sm font-medium text-gray-200">{email}</p>
        </div>
        <div className="flex items-center justify-end gap-3">
          <button onClick={onClose} className="px-3 py-2 text-sm text-gray-400 hover:text-gray-200">Close</button>
        </div>
      </div>
    </div>
  )
}
