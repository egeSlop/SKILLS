<?php

namespace App\Filament\Resources;

use Filament\Resources\Resource as FilamentResource;

/**
 * Filament allows access by default; every resource extends this so a
 * forgotten canAccess() hides the screen instead of exposing it.
 */
abstract class BaseResource extends FilamentResource
{
    public static function canAccess(): bool
    {
        return false;
    }
}
