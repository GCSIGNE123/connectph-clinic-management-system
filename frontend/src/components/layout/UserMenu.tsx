"use client";

import { useRouter } from "next/navigation";
import { LogOut, Settings, User as UserIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar } from "@/components/ui/avatar";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useLogout } from "@/features/auth/hooks/use-logout";

/**
 * User account dropdown shown in the top navigation. Reads the current
 * user via TanStack Query and exposes a real logout action.
 */
export function UserMenu() {
  const { data: user } = useCurrentUser();
  const logout = useLogout();
  const router = useRouter();

  const displayName = user ? `${user.firstName} ${user.lastName}` : "Signed in user";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger>
        <button
          type="button"
          className="flex items-center gap-2 rounded-md p-1 pr-2 text-sm hover:bg-accent"
        >
          <Avatar name={displayName} src={user?.avatarUrl} size="sm" />
          <span className="hidden max-w-[10rem] truncate font-medium sm:inline">
            {displayName}
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>{user?.email ?? "Account"}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/profile")}>
          <UserIcon className="h-4 w-4" aria-hidden="true" />
          Profile
        </DropdownMenuItem>
        {/* No separate account-settings page exists yet - the Profile page's
            "Change password" section is the only self-service account
            setting so far, so this also routes there rather than being a
            dead stub. */}
        <DropdownMenuItem onClick={() => router.push("/profile")}>
          <Settings className="h-4 w-4" aria-hidden="true" />
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem destructive onClick={() => logout.mutate()}>
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
