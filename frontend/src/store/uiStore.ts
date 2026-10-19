import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  duration?: number;
}

interface UIState {
  sidebarCollapsed: boolean;
  activeSKUPanel: string | null;
  activeCustomerPanel: string | null;
  sizeEditorOpen: boolean;
  sizeEditorSKU: string | null;
  financialValidationOpen: boolean;
  toasts: Toast[];
  confirmDialog: {
    open: boolean;
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    onConfirm?: () => void;
    onCancel?: () => void;
  } | null;

  // Actions
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setActiveSKUPanel: (skuId: string | null) => void;
  setActiveCustomerPanel: (customerId: string | null) => void;
  openSizeEditor: (skuId: string) => void;
  closeSizeEditor: () => void;
  setFinancialValidationOpen: (open: boolean) => void;
  
  // Toast actions
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
  clearToasts: () => void;
  
  // Confirm dialog
  showConfirmDialog: (options: {
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    onConfirm?: () => void;
    onCancel?: () => void;
  }) => void;
  closeConfirmDialog: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      sidebarCollapsed: false,
      activeSKUPanel: null,
      activeCustomerPanel: null,
      sizeEditorOpen: false,
      sizeEditorSKU: null,
      financialValidationOpen: false,
      toasts: [],
      confirmDialog: null,

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

      setActiveSKUPanel: (skuId) => set({ activeSKUPanel: skuId }),

      setActiveCustomerPanel: (customerId) =>
        set({ activeCustomerPanel: customerId }),

      openSizeEditor: (skuId) =>
        set({ sizeEditorOpen: true, sizeEditorSKU: skuId }),

      closeSizeEditor: () =>
        set({ sizeEditorOpen: false, sizeEditorSKU: null }),

      setFinancialValidationOpen: (open) =>
        set({ financialValidationOpen: open }),

      addToast: (toast) => {
        const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        set((state) => ({
          toasts: [...state.toasts, { ...toast, id }],
        }));
        if (toast.duration !== 0) {
          setTimeout(() => {
            get().removeToast(id);
          }, toast.duration || 5000);
        }
      },

      removeToast: (id) =>
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        })),

      clearToasts: () => set({ toasts: [] }),

      showConfirmDialog: (options) =>
        set({
          confirmDialog: {
            open: true,
            ...options,
          },
        }),

      closeConfirmDialog: () => set({ confirmDialog: null }),
    }),
    {
      name: 'ui-store',
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
);
